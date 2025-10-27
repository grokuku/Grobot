import logging
import asyncio
from celery import shared_task
from sqlalchemy.orm import Session
import json
import httpx
import os
import websockets
import time
from datetime import datetime
from croniter import croniter

from app.database.sql_session import SessionLocal
# MODIFIED: Added crud_bots and crud_settings
from app.database import crud_user_notes, crud_workflows, crud_mcp, crud_bots, crud_settings
from app.database.sql_models import LLMEvaluationRun, Workflow, Trigger
from app.schemas import chat_schemas
from app.core.agents.archivist import run_archivist
# MODIFIED: Import llm_manager and its LLMConfig
from app.core import llm_manager
from app.schemas.settings_schema import LLMEvaluationRunCreate

# --- ACE Framework Imports ---
# NOTE: These imports assume the ace-framework is installed and structured this way.
try:
    from ace.playbook import Playbook
    from ace.roles import Reflector, Curator
    from ace.adaptation import TaskEnvironment
    from ace.llm_providers.lite_llm import LiteLLMClient
    ACE_INSTALLED = True
except ImportError:
    ACE_INSTALLED = False
    # Define dummy classes if ACE is not installed to avoid server crashes
    class Playbook: pass
    class Reflector: pass
    class Curator: pass
    class TaskEnvironment: pass
    class LiteLLMClient: pass
# --- End ACE Imports ---


# Configuration du logging pour les tâches Celery
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - (CELERY_TASK) - %(message)s')
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

INTERNAL_API_BASE_URL = os.getenv("INTERNAL_API_BASE_URL", "http://app:8000")

# --- Asynchronous Helper for MCP Streaming ---
async def _handle_mcp_stream(ws_url: str) -> dict:
    # ... (This function is unchanged and correct)
    logger.info(f"  - Stream handler started. Connecting to WebSocket: {ws_url}")
    TOTAL_TIMEOUT_SECONDS = 600 # 10 minutes total timeout

    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            async with websockets.connect(ws_url) as websocket:
                async for message_str in websocket:
                    try:
                        message_data = json.loads(message_str)
                    except json.JSONDecodeError:
                        logger.warning(f"  - Received non-JSON message from stream: {message_str}")
                        continue

                    params = message_data.get("params", {})
                    if message_data.get("method") in ("stream/chunk", "stream/end"):
                        if error_obj := params.get("error"):
                            error_msg = error_obj.get("message", "Unknown stream error")
                            logger.error(f"  - Stream reported an error: {error_msg}")
                            raise RuntimeError(f"Tool stream error: {error_msg}")
                        
                        elif result_obj := params.get("result"):
                            logger.info("  - Received final result from stream.")
                            return result_obj

                    logger.debug(f"  - Stream progress message received: {message_data}")

    except asyncio.TimeoutError:
        logger.error(f"  - WebSocket stream timed out after {TOTAL_TIMEOUT_SECONDS} seconds.")
        raise ValueError("Stream ended without providing a final result (timeout).")
    except Exception as e:
        logger.error(f"  - Error during WebSocket stream handling: {e}", exc_info=True)
        raise
    
    raise ValueError("Stream ended without providing a final result.")


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

# --- START OF MODIFICATION: Final Corrected Value Resolver ---
def _resolve_value(value: any, step_results: dict):
    if isinstance(value, dict):
        if 'source_step_order' in value and 'output_key' in value:
            step_order = value['source_step_order']
            output_key = value['output_key']
            
            source_result = step_results.get(step_order)
            if source_result is None:
                raise ValueError(f"Could not find result for source step {step_order} (result was missing or None)")

            if 'content' in source_result and isinstance(source_result['content'], list):
                for item in source_result['content']:
                    if item.get("type") == "json" and isinstance(item.get("json"), dict):
                        json_payload = item["json"]
                        if output_key in json_payload:
                            return json_payload[output_key]
                    if item.get("type") == "image" and output_key == "image_url":
                        # MODIFICATION: Prefer 'source' (MCP standard) but fallback to 'image_url' for robustness.
                        return item.get("source") or item.get("image_url")

            if output_key in source_result:
                return source_result[output_key]

            raise ValueError(f"Could not find output key '{output_key}' in the result of step {step_order}")
        else:
            return {k: _resolve_value(v, step_results) for k, v in value.items()}
            
    elif isinstance(value, list):
        return [_resolve_value(item, step_results) for item in value]
        
    else:
        return value
# --- END OF MODIFICATION ---

# MODIFICATION: Removed retry parameters from the decorator
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
        
        for step in sorted_steps:
            current_step_for_logging = step
            logger.info(f"Executing step {step.step_order}: Tool '{step.tool_name}'")
            resolved_args = {}
            
            for param_name, mapping in step.parameter_mappings.items():
                resolved_args[param_name] = _resolve_value(mapping, step_results)

            if step.tool_name == "generate_prompt":
                if 'elements' in resolved_args and isinstance(resolved_args['elements'], str):
                    logger.info(f"Transforming 'elements' parameter from string to list for tool '{step.tool_name}'.")
                    elements_str = resolved_args['elements']
                    resolved_args['elements'] = [e.strip() for e in elements_str.split(',') if e.strip()]
            elif step.tool_name == "generate_image":
                if 'style_names' in resolved_args and isinstance(resolved_args['style_names'], str):
                    logger.info(f"Transforming 'style_names' parameter from string to list for tool '{step.tool_name}'.")
                    style_str = resolved_args['style_names']
                    resolved_args['style_names'] = [s.strip() for s in style_str.split(',') if s.strip()]

            tool_result = None
            if step.mcp_server_id is None:
                if step.tool_name == "post_to_discord":
                    payload = {
                        "bot_id": workflow.bot_id,
                        "channel_id": resolved_args.get("channel_id"),
                        "message_content": resolved_args.get("message_content"),
                        "attachments": resolved_args.get("attachments")
                    }
                    
                    with httpx.Client() as client:
                        response = client.post(f"{INTERNAL_API_BASE_URL}/api/workflows/outputs/discord", json=payload, timeout=30)
                        response.raise_for_status()
                        tool_result = response.json()
                        logger.info(f"Successfully forwarded to internal tool '{step.tool_name}'.")
                else:
                    raise NotImplementedError(f"Unknown internal tool '{step.tool_name}' configured in step {step.step_order}. Execution cannot continue.")
            else:
                mcp_server = crud_mcp.get_mcp_server(db, server_id=step.mcp_server_id)
                if not mcp_server:
                    raise ValueError(f"MCP Server with id {step.mcp_server_id} not found for step {step.step_order}")
                
                json_rpc_payload = {
                    "jsonrpc": "2.0",
                    "id": f"workflow-{workflow_id}-step-{step.step_order}",
                    "method": "tools/call",
                    "params": {"name": step.tool_name, "arguments": resolved_args}
                }
                mcp_server_url = f"http://{mcp_server.host}:{mcp_server.port}{mcp_server.rpc_endpoint_path}"
                
                with httpx.Client() as client:
                    response = client.post(mcp_server_url, json=json_rpc_payload, timeout=600)
                    response.raise_for_status()
                    response_data = response.json()

                    # --- START OF MODIFICATION: Corrected Response Handling ---
                    # 1. Check for an explicit error response from the tool
                    if "error" in response_data:
                        error_details = response_data['error']
                        raise RuntimeError(f"MCP tool '{step.tool_name}' returned an explicit error: {error_details}")
                    
                    # 2. Check for the specific 'stream/start' method, which is a valid non-result response
                    elif response_data.get("method") == "stream/start":
                        params = response_data.get("params", {})
                        ws_url = params.get("ws_url")
                        if not ws_url:
                            raise ValueError(f"MCP server sent 'stream/start' without a 'ws_url' for tool '{step.tool_name}'. Body: {response_data}")
                        
                        logger.info(f"Detected streaming response for tool '{step.tool_name}'. Initializing stream handler.")
                        tool_result = asyncio.run(_handle_mcp_stream(ws_url))
                    
                    # 3. Check for a standard synchronous result
                    elif "result" in response_data:
                        tool_result = response_data["result"]
                        logger.info(f"Successfully executed MCP tool '{step.tool_name}' with a synchronous result.")
                    
                    # 4. If none of the above, the response format is unknown and invalid
                    else:
                        raise ValueError(f"Invalid or unhandled JSON-RPC response from MCP server for tool '{step.tool_name}'. Body: {response_data}")
                    # --- END OF MODIFICATION ---
            
            step_results[step.step_order] = tool_result

        logger.info(f"Workflow '{workflow.name}' (id: {workflow_id}) executed successfully.")
    except Exception as e:
        step_order_info = "N/A"
        if current_step_for_logging:
            step_order_info = current_step_for_logging.step_order
        logger.error(f"Workflow execution failed for workflow_id {workflow_id} at step {step_order_info}. Root cause: {e}", exc_info=True)
        # MODIFICATION: Removed self.retry(exc=e)
    finally:
        db.close()

@shared_task(ignore_result=True)
def schedule_cron_workflows():
    """
    This task runs periodically (e.g., every minute) to check for and
    trigger workflows based on their cron schedule.
    """
    logger.info("CRON_SCHEDULER: Checking for workflows to run...")
    db: Session = SessionLocal()
    try:
        # Fetch all enabled workflows that have a 'cron' trigger
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
                if not cron_string:
                    continue
                
                # Use last_run_at if available, otherwise assume it's the first run
                last_run = workflow.last_run_at or now
                
                # croniter helps determine if the job should have run by now
                cron = croniter(cron_string, last_run)
                next_scheduled_run = cron.get_next(datetime)

                if next_scheduled_run <= now:
                    logger.info(f"CRON_SCHEDULER: Triggering workflow '{workflow.name}' (id: {workflow.id})")
                    execute_workflow.delay(workflow_id=workflow.id)
                    
                    # IMPORTANT: Update the last run time to prevent re-triggering
                    workflow.last_run_at = now
                    db.add(workflow)
                    triggered_count += 1

            except Exception as e:
                logger.error(f"CRON_SCHEDULER: Failed to evaluate cron for workflow {workflow.id}: {e}")

        if triggered_count > 0:
            db.commit()

        logger.info(f"CRON_SCHEDULER: Finished check. Triggered {triggered_count} workflow(s).")

    finally:
        db.close()

def _generate_context_ballast(token_count: int) -> str:
    """Generates plausible-looking text to pad the context."""
    # This is a simplistic implementation. A more advanced version could use
    # a small, fast model or a library like 'faker' to generate more realistic text.
    lorem_ipsum = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum."
    repetitions = (token_count // (len(lorem_ipsum.split()) + 1)) + 1
    return " ".join([lorem_ipsum] * repetitions)

async def _run_single_evaluation_case(config: llm_manager.LLMConfig, test_case: dict, ballast_tokens: int) -> dict:
    """Runs a single test case and returns the results."""
    # This is a placeholder for the detailed test logic.
    # We will implement the "Gabarits de Contexte Réaliste" here.
    system_prompt = test_case.get("system_prompt", "You are a helpful assistant.")
    user_message = test_case.get("user_message", "")
    
    ballast = _generate_context_ballast(ballast_tokens)
    full_user_message = f"{ballast}\n\n{user_message}"
    
    messages = [{"role": "user", "content": full_user_message}]
    
    start_time = time.time()
    
    # In a real scenario, we'd add validation logic here (e.g., check if JSON is valid).
    is_reliable = True 
    response_content = "Placeholder response"
    
    try:
        response_content = await llm_manager.call_llm(
            config=config,
            system_prompt=system_prompt,
            messages=messages,
            json_mode=test_case.get("json_mode", False)
        )
        # Add validation logic here based on test_case['validation']
        
    except Exception as e:
        is_reliable = False
        response_content = f"Error: {e}"

    end_time = time.time()
    response_ms = (end_time - start_time) * 1000
    
    # Placeholder for token calculation
    tokens_generated = len(response_content.split())
    tokens_per_second = tokens_generated / (response_ms / 1000) if response_ms > 0 else 0
    
    return {
        "prompt_tokens": ballast_tokens + len(user_message.split()),
        "response_ms": round(response_ms, 2),
        "tokens_per_second": round(tokens_per_second, 2),
        "is_reliable": is_reliable,
        "response": response_content[:500] # Truncate for storage
    }

@shared_task(bind=True)
def run_llm_evaluation(self, evaluation_request_data: dict):
    """
    Celery task to run a comprehensive evaluation of a given LLM configuration.
    """
    task_id = self.request.id
    logger.info(f"Starting LLM evaluation for task_id: {task_id}")
    
    db: Session = SessionLocal()
    try:
        # --- CORRECTED ---
        # Use the correctly imported LLMEvaluationRun model
        evaluation_run = db.query(LLMEvaluationRun).filter_by(task_id=task_id).first()
        if not evaluation_run:
            logger.error(f"Could not find LLMEvaluationRun record for task_id {task_id}. Aborting.")
            return

        # 1. Update status to RUNNING
        evaluation_run.status = 'RUNNING'
        evaluation_run.started_at = datetime.utcnow()
        db.commit()

        request_data = LLMEvaluationRunCreate(**evaluation_request_data)
        
        # This is where we'll define our test suites later
        # For now, a simple placeholder test
        test_suites = {
            "decisional": [{"name": "Simple Gatekeeper Test", "user_message": "Should I respond to this?", "json_mode": True}],
            "tools": [{"name": "Simple JSON Extraction", "user_message": "Generate an image of a cat.", "json_mode": True}],
            "output_client": [{"name": "Simple Summarization", "user_message": "Summarize this for me."}]
        }
        
        scenarios = test_suites.get(request_data.llm_category, [])
        if not scenarios:
            raise ValueError(f"No test scenarios defined for category: {request_data.llm_category}")

        all_results = []
        context_window_tests = [2048, 4096, 8192] # Example context windows
        prompt_size_percentages = [0.10, 0.50, 0.90] # 10%, 50%, 90%

        for window_size in context_window_tests:
            config = llm_manager.LLMConfig(
                server_url=request_data.llm_server_url,
                model_name=request_data.llm_model_name,
                context_window=window_size
            )
            for percentage in prompt_size_percentages:
                for scenario in scenarios:
                    ballast_size = int(window_size * percentage)
                    logger.info(f"Testing window: {window_size}, prompt fill: {percentage*100}%, scenario: '{scenario['name']}'")
                    
                    # Use asyncio.run to execute the async test case
                    result = asyncio.run(_run_single_evaluation_case(config, scenario, ballast_size))
                    
                    all_results.append({
                        "window_size": window_size,
                        "prompt_percentage": percentage,
                        "scenario_name": scenario['name'],
                        **result
                    })

        # 2. Process and save final results
        total_tests = len(all_results)
        successful_tests = sum(1 for r in all_results if r['is_reliable'])
        
        evaluation_run.summary_reliability_score = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
        evaluation_run.summary_avg_response_ms = sum(r['response_ms'] for r in all_results) / total_tests if total_tests > 0 else 0
        evaluation_run.summary_avg_tokens_per_second = sum(r['tokens_per_second'] for r in all_results) / total_tests if total_tests > 0 else 0
        
        evaluation_run.results_data = {"details": all_results}
        evaluation_run.status = 'COMPLETED'
        evaluation_run.completed_at = datetime.utcnow()
        db.commit()
        
        logger.info(f"LLM evaluation task {task_id} completed successfully.")

    except Exception as e:
        logger.error(f"LLM evaluation task {task_id} failed: {e}", exc_info=True)
        if db.is_active:
            # --- CORRECTED ---
            # Use the correctly imported LLMEvaluationRun model here as well
            evaluation_run = db.query(LLMEvaluationRun).filter_by(task_id=task_id).first()
            if evaluation_run:
                evaluation_run.status = 'FAILED'
                evaluation_run.error_message = str(e)
                evaluation_run.completed_at = datetime.utcnow()
                db.commit()
    finally:
        db.close()

# --- START: ACE Integration (Phase 1) ---

# Define a custom TaskEnvironment for self-reflection
class SelfReflectionEnvironment(TaskEnvironment):
    """
    An ACE TaskEnvironment for a bot to reflect on its own performance
    in a given interaction without external ground truth.
    """
    def __init__(self, interaction_context: dict):
        self.history = interaction_context.get("history", [])
        self.final_response = interaction_context.get("final_response", "")
        if not self.history or not self.final_response:
            raise ValueError("Interaction context must contain 'history' and 'final_response'")

    def get_task_prompt(self) -> str:
        """
        Formats the entire interaction as a single block of text
        for the Reflector to analyze.
        """
        formatted_history = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in self.history])
        return (
            "Please analyze the following conversation and the bot's final response. "
            "Identify key insights about what made the response good or bad, and suggest "
            "specific, reusable strategies for the future.\n\n"
            "--- Conversation History ---\n"
            f"{formatted_history}\n\n"
            "--- Bot's Final Response ---\n"
            f"{self.final_response}"
        )

    def get_feedback(self, generated_response: str) -> tuple[float, str]:
        """
        In self-reflection mode, this method is not used as there is no
        external feedback loop. The initial analysis is done by the Reflector
        on the get_task_prompt() content.
        """
        return 0.0, "No external feedback available in self-reflection mode."


@shared_task(ignore_result=True)
def learn_from_interaction(bot_id: int, interaction_context_json: str):
    """
    A Celery task that uses the ACE framework to learn from a completed
    conversation and update the bot's playbook.
    """
    if not ACE_INSTALLED:
        logger.warning("ACE framework not installed. Skipping learn_from_interaction task.")
        return

    logger.info(f"ACE: Starting learning cycle for bot_id: {bot_id}")
    db: Session = SessionLocal()
    try:
        # 1. Load data and configuration
        interaction_context = json.loads(interaction_context_json)
        bot = crud_bots.get_bot(db, bot_id)
        if not bot:
            logger.error(f"ACE: Bot with id {bot_id} not found.")
            return
        
        global_settings = crud_settings.get_global_settings(db)
        llm_config = llm_manager.get_llm_config_for_category(
            bot=bot,
            global_settings=global_settings,
            category='output_client' # Use a powerful model for reflection
        )

        # 2. Setup ACE components
        llm_client = LiteLLMClient(
            model=llm_config.model_name,
            api_base=llm_config.server_url
        )
        reflector = Reflector(llm_client)
        curator = Curator(llm_client)
        environment = SelfReflectionEnvironment(interaction_context)

        # 3. Load or create the bot's playbook
        playbook_dir = "/app/data/playbooks"
        os.makedirs(playbook_dir, exist_ok=True)
        playbook_path = os.path.join(playbook_dir, f"{bot_id}.json")
        
        if os.path.exists(playbook_path):
            logger.info(f"ACE: Loading existing playbook from {playbook_path}")
            playbook = Playbook.from_file(playbook_path)
        else:
            logger.info(f"ACE: Creating new playbook for bot {bot_id}")
            playbook = Playbook(bot_id=str(bot_id), name=f"{bot.name}'s Playbook")

        # 4. Run the learning cycle: Reflect -> Curate
        task_prompt = environment.get_task_prompt()
        
        # The 'Reflector' analyzes the outcome
        reflection = reflector.reflect(
            playbook=playbook,
            task_prompt=task_prompt,
            # In this phase, the bot's response is the subject of analysis
            llm_response=interaction_context['final_response']
        )
        logger.info(f"ACE: Reflector produced key insight: '{reflection.key_insight}'")

        # The 'Curator' decides on playbook updates
        delta_batch = curator.curate(
            playbook=playbook,
            reflection=reflection
        )
        
        if not delta_batch.operations:
            logger.info("ACE: Curator decided no changes are needed for the playbook.")
        else:
            logger.info(f"ACE: Curator proposed {len(delta_batch.operations)} changes. Applying to playbook.")
            # 5. Apply changes and save the playbook
            playbook.apply_delta_batch(delta_batch)
            playbook.save_to_file(playbook_path)
            logger.info(f"ACE: Playbook for bot {bot_id} successfully updated and saved.")

    except Exception as e:
        logger.error(f"ACE: An error occurred during the learning cycle for bot {bot_id}: {e}", exc_info=True)
    finally:
        db.close()

# --- END: ACE Integration (Phase 1) ---