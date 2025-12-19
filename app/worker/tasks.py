#### Fichier: app/worker/tasks.py
import logging
import asyncio
from celery import shared_task
from sqlalchemy.orm import Session
import json
import httpx
import os
import time
from datetime import datetime
from croniter import croniter

# --- NEW: MCP-Use Import ---
from mcp_use import MCPClient
# ---------------------------

from app.database.sql_session import SessionLocal
from app.database import crud_user_notes, crud_workflows, crud_mcp, crud_bots, crud_settings
from app.database.sql_models import LLMEvaluationRun, Workflow, Trigger
from app.schemas import chat_schemas
from app.core.agents.archivist import run_archivist
from app.core import llm_manager
from app.schemas.settings_schema import LLMEvaluationRunCreate

# --- ACE Framework Imports ---
try:
    from ace.playbook import Playbook
    from ace.roles import Reflector, Curator
    from ace.adaptation import TaskEnvironment
    from ace.llm_providers.lite_llm import LiteLLMClient
    ACE_INSTALLED = True
except ImportError:
    ACE_INSTALLED = False
    class Playbook: pass
    class Reflector: pass
    class Curator: pass
    class TaskEnvironment: pass
    class LiteLLMClient: pass

# Logging Setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - (CELERY_TASK) - %(message)s')
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

INTERNAL_API_BASE_URL = os.getenv("INTERNAL_API_BASE_URL", "http://app:8000")

@shared_task(ignore_result=True)
def run_archivist_task(chat_request_json: str, final_response: str):
    db: Session = SessionLocal()
    try:
        chat_request_data = json.loads(chat_request_json)
        chat_request = chat_schemas.ChatRequest(**chat_request_data)
        run_archivist(db, chat_request, final_response)
    except Exception as e:
        logger.error(f"Error in run_archivist_task: {e}", exc_info=True)
    finally:
        db.close()

# --- Helper: Value Resolver ---
def _resolve_value(value: any, step_results: dict):
    if isinstance(value, dict):
        if 'source_step_order' in value and 'output_key' in value:
            step_order = value['source_step_order']
            output_key = value['output_key']
            
            source_result = step_results.get(step_order)
            if source_result is None:
                raise ValueError(f"Could not find result for source step {step_order} (result was missing or None)")

            # Handle MCP Content List structure
            if isinstance(source_result, dict) and 'text_content' in source_result and output_key == 'text_content':
                return source_result['text_content']

            # Fallback for structured data (if tool returned JSON/Dict)
            if isinstance(source_result, dict) and output_key in source_result:
                return source_result[output_key]
                
            # If the result itself is the value we want (simple return)
            if output_key == "result" and "result" not in source_result:
                 return source_result

            raise ValueError(f"Could not find output key '{output_key}' in the result of step {step_order}")
        else:
            return {k: _resolve_value(v, step_results) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_value(item, step_results) for item in value]
    else:
        return value

# --- REFACTORED: Execute Workflow using MCP-Use ---
@shared_task(bind=True)
def execute_workflow(self, workflow_id: int):
    logger.info(f"Starting execution for workflow_id: {workflow_id}")
    db: Session = SessionLocal()
    step_results = {}
    current_step_for_logging = None
    
    try:
        workflow = crud_workflows.get_workflow(db, workflow_id=workflow_id)
        if not workflow:
            logger.error(f"Workflow with id {workflow_id} not found.")
            return
        if not workflow.is_enabled:
            logger.warning(f"Workflow '{workflow.name}' (id: {workflow_id}) is disabled. Skipping execution.")
            return
        
        sorted_steps = sorted(workflow.steps, key=lambda s: s.step_order)
        
        # Use asyncio.run to execute async MCP calls within the synchronous Celery task
        async def _run_steps():
            nonlocal step_results, current_step_for_logging
            
            # Pre-fetch all necessary MCP servers to build config
            # (Optimization: We could do this step-by-step, but building one client is cleaner if possible,
            # though here we might need to build ad-hoc clients if steps use different servers not easily grouped).
            # For simplicity in this task, we'll instantiate a client per step if it's an external tool.
            
            for step in sorted_steps:
                current_step_for_logging = step
                logger.info(f"Executing step {step.step_order}: Tool '{step.tool_name}'")
                
                # Resolve Arguments
                resolved_args = {}
                for param_name, mapping in step.parameter_mappings.items():
                    resolved_args[param_name] = _resolve_value(mapping, step_results)

                # Special Transformations (Legacy logic preserved)
                if step.tool_name == "generate_prompt" and isinstance(resolved_args.get('elements'), str):
                     resolved_args['elements'] = [e.strip() for e in resolved_args['elements'].split(',') if e.strip()]
                elif step.tool_name == "generate_image" and isinstance(resolved_args.get('style_names'), str):
                     resolved_args['style_names'] = [s.strip() for s in resolved_args['style_names'].split(',') if s.strip()]

                tool_result = None
                
                # --- INTERNAL TOOLS (e.g., Discord Post) ---
                if step.mcp_server_id is None:
                    if step.tool_name == "post_to_discord":
                        payload = {
                            "bot_id": workflow.bot_id,
                            "channel_id": resolved_args.get("channel_id"),
                            "message_content": resolved_args.get("message_content"),
                            "attachments": resolved_args.get("attachments")
                        }
                        async with httpx.AsyncClient() as client:
                            response = await client.post(f"{INTERNAL_API_BASE_URL}/api/workflows/outputs/discord", json=payload, timeout=30)
                            response.raise_for_status()
                            tool_result = response.json()
                            logger.info(f"Successfully forwarded to internal tool '{step.tool_name}'.")
                    else:
                        raise NotImplementedError(f"Unknown internal tool '{step.tool_name}' configured in step {step.step_order}.")
                
                # --- EXTERNAL MCP TOOLS (via MCP-Use) ---
                else:
                    mcp_server = crud_mcp.get_mcp_server(db, server_id=step.mcp_server_id)
                    if not mcp_server:
                        raise ValueError(f"MCP Server with id {step.mcp_server_id} not found for step {step.step_order}")
                    
                    base_url = f"http://{mcp_server.host}:{mcp_server.port}{mcp_server.rpc_endpoint_path}"
                    
                    config = {
                        "mcpServers": {
                            "default": {
                                "transport": "sse",
                                "url": base_url
                            }
                        }
                    }
                    
                    client = MCPClient(config)
                    try:
                        await client.create_all_sessions()
                        session = client.get_session("default")
                        if not session:
                             raise Exception("Failed to create session with MCP server.")
                        
                        # Call Tool
                        result_obj = await session.call_tool(step.tool_name, resolved_args)
                        
                        # Process Result
                        # We convert the MCP result object into a dictionary for step_results
                        content_list = []
                        raw_data = {} # Try to reconstruct JSON if the tool returns it as text
                        
                        if hasattr(result_obj, 'content') and isinstance(result_obj.content, list):
                            for item in result_obj.content:
                                if hasattr(item, 'type') and hasattr(item, 'text') and item.type == 'text':
                                    content_list.append(item.text)
                                    # Try parsing as JSON for data-centric tools
                                    try:
                                        import json
                                        data = json.loads(item.text)
                                        if isinstance(data, dict):
                                            raw_data.update(data)
                                    except:
                                        pass
                                else:
                                    content_list.append(str(item))
                        
                        tool_result = {
                            "text_content": "\n".join(content_list),
                            **raw_data # Merge parsed JSON data so _resolve_value can find keys
                        }
                        
                        logger.info(f"Successfully executed MCP tool '{step.tool_name}'.")

                    except Exception as e:
                        logger.error(f"MCP Execution Error for {step.tool_name}: {e}")
                        raise
                    finally:
                        # cleanup if needed
                        pass

                step_results[step.step_order] = tool_result
        
        # Run the async loop
        asyncio.run(_run_steps())
        logger.info(f"Workflow '{workflow.name}' (id: {workflow_id}) executed successfully.")

    except Exception as e:
        step_order_info = current_step_for_logging.step_order if current_step_for_logging else "N/A"
        logger.error(f"Workflow execution failed for workflow_id {workflow_id} at step {step_order_info}. Root cause: {e}", exc_info=True)
    finally:
        db.close()

@shared_task(ignore_result=True)
def schedule_cron_workflows():
    logger.info("CRON_SCHEDULER: Checking for workflows to run...")
    db: Session = SessionLocal()
    try:
        cron_workflows = db.query(Workflow).join(Trigger).filter(
            Workflow.is_enabled == True,
            Trigger.trigger_type == 'cron'
        ).all()

        if not cron_workflows:
            logger.info("CRON_SCHEDULER: No active cron workflows found.")
            return

        now = datetime.utcnow()
        triggered_count = 0
        for workflow in cron_workflows:
            try:
                cron_string = workflow.trigger.config.get("cron_string")
                if not cron_string: continue
                
                last_run = workflow.last_run_at or now
                cron = croniter(cron_string, last_run)
                next_scheduled_run = cron.get_next(datetime)

                if next_scheduled_run <= now:
                    logger.info(f"CRON_SCHEDULER: Triggering workflow '{workflow.name}' (id: {workflow.id})")
                    execute_workflow.delay(workflow_id=workflow.id)
                    workflow.last_run_at = now
                    db.add(workflow)
                    triggered_count += 1
            except Exception as e:
                logger.error(f"CRON_SCHEDULER: Failed to evaluate cron for workflow {workflow.id}: {e}")

        if triggered_count > 0:
            db.commit()
    finally:
        db.close()

def _generate_context_ballast(token_count: int) -> str:
    lorem_ipsum = "Lorem ipsum dolor sit amet, consectetur adipiscing elit..."
    repetitions = (token_count // (len(lorem_ipsum.split()) + 1)) + 1
    return " ".join([lorem_ipsum] * repetitions)

async def _run_single_evaluation_case(config: llm_manager.LLMConfig, test_case: dict, ballast_tokens: int) -> dict:
    # ... (Unchanged logic for evaluation)
    system_prompt = test_case.get("system_prompt", "You are a helpful assistant.")
    user_message = test_case.get("user_message", "")
    ballast = _generate_context_ballast(ballast_tokens)
    full_user_message = f"{ballast}\n\n{user_message}"
    messages = [{"role": "user", "content": full_user_message}]
    
    start_time = time.time()
    is_reliable = True 
    response_content = "Placeholder response"
    
    try:
        response_content = await llm_manager.call_llm(
            config=config,
            system_prompt=system_prompt,
            messages=messages,
            json_mode=test_case.get("json_mode", False)
        )
    except Exception as e:
        is_reliable = False
        response_content = f"Error: {e}"

    end_time = time.time()
    response_ms = (end_time - start_time) * 1000
    tokens_generated = len(response_content.split())
    tokens_per_second = tokens_generated / (response_ms / 1000) if response_ms > 0 else 0
    
    return {
        "prompt_tokens": ballast_tokens + len(user_message.split()),
        "response_ms": round(response_ms, 2),
        "tokens_per_second": round(tokens_per_second, 2),
        "is_reliable": is_reliable,
        "response": response_content[:500] 
    }

@shared_task(bind=True)
def run_llm_evaluation(self, evaluation_request_data: dict):
    # ... (Unchanged logic for evaluation task)
    task_id = self.request.id
    db: Session = SessionLocal()
    try:
        evaluation_run = db.query(LLMEvaluationRun).filter_by(task_id=task_id).first()
        if not evaluation_run: return

        evaluation_run.status = 'RUNNING'
        evaluation_run.started_at = datetime.utcnow()
        db.commit()

        request_data = LLMEvaluationRunCreate(**evaluation_request_data)
        
        # Placeholder Test Suites
        test_suites = {
            "decisional": [{"name": "Simple Gatekeeper Test", "user_message": "Should I respond?", "json_mode": True}],
            "tools": [{"name": "Simple JSON Extraction", "user_message": "Image of a cat.", "json_mode": True}],
            "output_client": [{"name": "Simple Summarization", "user_message": "Summarize."}]
        }
        
        scenarios = test_suites.get(request_data.llm_category, [])
        all_results = []
        context_window_tests = [2048] # Reduced for quick testing
        prompt_size_percentages = [0.10]

        for window_size in context_window_tests:
            config = llm_manager.LLMConfig(
                server_url=request_data.llm_server_url,
                model_name=request_data.llm_model_name,
                context_window=window_size
            )
            for percentage in prompt_size_percentages:
                for scenario in scenarios:
                    ballast_size = int(window_size * percentage)
                    result = asyncio.run(_run_single_evaluation_case(config, scenario, ballast_size))
                    all_results.append({
                        "window_size": window_size, "prompt_percentage": percentage,
                        "scenario_name": scenario['name'], **result
                    })

        total_tests = len(all_results)
        successful_tests = sum(1 for r in all_results if r['is_reliable'])
        
        evaluation_run.summary_reliability_score = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        evaluation_run.results_data = {"details": all_results}
        evaluation_run.status = 'COMPLETED'
        evaluation_run.completed_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        logger.error(f"LLM evaluation task failed: {e}")
        if db.is_active:
            evaluation_run = db.query(LLMEvaluationRun).filter_by(task_id=task_id).first()
            if evaluation_run:
                evaluation_run.status = 'FAILED'
                evaluation_run.error_message = str(e)
                evaluation_run.completed_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()

# --- ACE Integration (Phase 1) ---
class SelfReflectionEnvironment(TaskEnvironment):
    def __init__(self, interaction_context: dict):
        self.history = interaction_context.get("history", [])
        self.final_response = interaction_context.get("final_response", "")

    def get_task_prompt(self) -> str:
        formatted_history = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in self.history])
        return f"Analyze conversation:\n{formatted_history}\n\nResponse:\n{self.final_response}"

    def get_feedback(self, generated_response: str) -> tuple[float, str]:
        return 0.0, "No external feedback."

@shared_task(ignore_result=True)
def learn_from_interaction(bot_id: int, interaction_context_json: str):
    if not ACE_INSTALLED: return
    db: Session = SessionLocal()
    try:
        interaction_context = json.loads(interaction_context_json)
        bot = crud_bots.get_bot(db, bot_id)
        if not bot: return
        
        global_settings = crud_settings.get_global_settings(db)
        llm_config = llm_manager.get_llm_config_for_category(bot, global_settings, 'output_client')

        llm_client = LiteLLMClient(model=llm_config.model_name, api_base=llm_config.server_url)
        reflector = Reflector(llm_client)
        curator = Curator(llm_client)
        environment = SelfReflectionEnvironment(interaction_context)

        playbook_path = f"/app/data/playbooks/{bot_id}.json"
        if os.path.exists(playbook_path):
            playbook = Playbook.from_file(playbook_path)
        else:
            playbook = Playbook(bot_id=str(bot_id), name=f"{bot.name}'s Playbook")

        reflection = reflector.reflect(playbook, environment.get_task_prompt(), interaction_context['final_response'])
        delta_batch = curator.curate(playbook, reflection)
        
        if delta_batch.operations:
            playbook.apply_delta_batch(delta_batch)
            playbook.save_to_file(playbook_path)
    except Exception as e:
        logger.error(f"ACE error: {e}")
    finally:
        db.close()