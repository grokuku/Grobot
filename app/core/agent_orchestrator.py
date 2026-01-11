import logging
from typing import Union, List, Dict, Any, Optional, AsyncGenerator
import asyncio
import json
import os
import re
from pydantic import BaseModel

# --- NEW: MCP-Use Import & HTTPX for Exceptions ---
from mcp_use import MCPClient
import httpx
# ---------------------------

from sqlalchemy.orm import Session

from app.core import llm_manager
from app.core.agents import prompts, synthesizer

# Schema Imports
from app.schemas.chat_schemas import (
    ProcessMessageRequest,
    StopResponse,
    ClarifyResponse,
    AcknowledgeAndExecuteResponse,
    SynthesizeResponse,
    PlannerResult,
    ChatMessage # Import needed for constructing the message
)

# Database CRUD Imports
from app.database import crud_bots, crud_mcp, crud_settings, sql_models

# ACE Framework Import
try:
    from ace.playbook import Playbook
    ACE_INSTALLED = True
except ImportError:
    ACE_INSTALLED = False
    # Dummy class to prevent runtime errors if ACE is not present
    class Playbook: pass

logger = logging.getLogger("app.core.agent_orchestrator")

# --- Internal Pydantic models for response validation ---

class GatekeeperResponse(BaseModel):
    should_respond: bool
    reason: str

class ToolIdentifierResponse(BaseModel):
    required_tools: List[str]

# --- Helpers ---

def _clean_json_response(raw_response: str) -> str:
    """
    Cleans the LLM response to extract only the JSON part.
    Removes <think> blocks and extracts the outermost JSON object or array.
    """
    if not raw_response:
        return "{}"
    
    # 1. Remove DeepSeek reasoning blocks <think>...</think>
    cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL)
    
    # 2. Robust Extraction: find the outermost braces or brackets
    # This handles nested structures correctly unlike a non-greedy regex
    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")
    
    # Determine which starts first to handle both objects and lists
    start_idx = -1
    end_idx = -1
    
    if start_obj != -1 and (start_arr == -1 or start_obj < start_arr):
        start_idx = start_obj
        end_idx = cleaned.rfind("}")
    elif start_arr != -1:
        start_idx = start_arr
        end_idx = cleaned.rfind("]")
        
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        return cleaned[start_idx:end_idx+1]
    
    return cleaned.strip()

def _load_bot_playbook_content(bot_id: int) -> str:
    """
    Loads the ACE Playbook for the given bot and returns it formatted as a prompt string.
    Returns an empty string if ACE is not installed or the playbook doesn't exist.
    """
    if not ACE_INSTALLED:
        return ""
    
    # Path matches the one used in tasks.py
    playbook_path = f"/app/data/playbooks/{bot_id}.json"
    
    if not os.path.exists(playbook_path):
        return ""
        
    try:
        playbook = Playbook.from_file(playbook_path)
        return playbook.as_prompt()
    except Exception as e:
        logger.error(f"Failed to load ACE playbook for bot {bot_id}: {e}")
        return ""

# --- Orchestrator Logic ---

async def process_user_message(
    db: Session,
    request: ProcessMessageRequest
) -> Union[StopResponse, ClarifyResponse, AcknowledgeAndExecuteResponse, SynthesizeResponse]:
    """
    Orchestrates the agent chain to process a user's message using categorized LLMs.
    """
    logger.info(f"Orchestrator starting for message {request.message_id} in channel {request.channel_id}")

    bot = crud_bots.get_bot(db=db, bot_id=request.bot_id)
    if not bot:
        return StopResponse(reason=f"Bot with ID {request.bot_id} not found.")
    
    global_settings = crud_settings.get_global_settings(db)
    
    # Load Playbook content early for use in Planner AND Tool Identifier
    playbook_content = _load_bot_playbook_content(bot.id)

    # --- FIX: CONSTRUCT FULL HISTORY (History + Current Message) ---
    # The request.history does NOT contain the current message. We must append it
    # so the agents can see what the user actually said.
    current_message = ChatMessage(
        role="user", 
        content=request.message_content, 
        name=request.user_display_name
    )
    # We use a list of dicts for the LLM calls to be compatible
    full_history_dicts = [msg.model_dump() for msg in request.history]
    full_history_dicts.append(current_message.model_dump())

    # --- 1. Gatekeeper Step (Category: Decisional) ---
    bypass_gatekeeper = request.is_direct_message or request.is_direct_mention
    if not bypass_gatekeeper:
        logger.info("Running Gatekeeper for ambient message...")
        
        # Resolve config and call LLM
        decisional_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_DECISIONAL)
        gatekeeper_prompt = prompts.GATEKEEPER_SYSTEM_PROMPT.format(bot_name=bot.name)
        # FIX: Use full_history_dicts
        response_str = await llm_manager.call_llm(decisional_config, gatekeeper_prompt, full_history_dicts, json_mode=True)
        
        cleaned_response = _clean_json_response(response_str)
        try:
            gatekeeper_decision = GatekeeperResponse.model_validate_json(cleaned_response)
            if not gatekeeper_decision.should_respond:
                logger.info(f"Gatekeeper decided not to respond. Reason: {gatekeeper_decision.reason}. Stopping.")
                return StopResponse(reason=gatekeeper_decision.reason)
            logger.info("Gatekeeper approved the response. Proceeding.")
        except Exception as e:
            logger.error(f"Failed to parse Gatekeeper response: {e}. Assuming NO response. Raw: '{response_str}'")
            return StopResponse(reason="Internal error in Gatekeeper response parsing.")
    else:
        logger.info(f"Bypassing Gatekeeper due to direct message or mention.")

    # --- 2. Tool Identification Step (Category: Tools) ---
    logger.info("--- STARTING TOOL IDENTIFICATION STEP ---")
    available_tools = await get_available_tools_for_bot(db, bot.id)
    
    # Debug log (reverted to debug level)
    logger.debug(f"Available tools for bot {bot.id}: {[t['name'] for t in available_tools]}")
    
    tools_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_TOOLS)
    logger.info(f"Tool Identifier using model: {tools_config.model_name} at {tools_config.server_url}")

    # --- IMPROVED TOOL LIST FORMATTING ---
    tools_entries = []
    for tool in available_tools:
        name = tool.get('name', 'unknown')
        desc = tool.get('description', 'No description')
        
        # Extract argument keys from schema to give the LLM a hint
        input_schema = tool.get('inputSchema', {})
        properties = input_schema.get('properties', {})
        arg_keys = list(properties.keys()) if properties else []
        
        args_str = ", ".join(arg_keys) if arg_keys else "None"
        tools_entries.append(f"- {name}: {desc} (Arguments: {args_str})")
        
    tools_list_str = "\n".join(tools_entries)
    
    # Inject Playbook content into Tool Identifier
    tool_id_prompt = prompts.TOOL_IDENTIFIER_SYSTEM_PROMPT.format(
        tools_list=tools_list_str,
        ace_playbook=playbook_content
    )
    
    logger.info("Calling LLM for Tool Identifier...")
    logger.debug(f"Tool Identifier Prompt Preview: {tool_id_prompt[:200]}...")

    try:
        # FIX: Use full_history_dicts
        response_str = await llm_manager.call_llm(tools_config, tool_id_prompt, full_history_dicts, json_mode=True)
        logger.info("LLM Response received for Tool Identifier.")
        logger.debug(f"Raw Tool Identifier Response: {response_str}")
    except Exception as llm_error:
        logger.error(f"CRITICAL ERROR during Tool Identifier LLM call: {llm_error}", exc_info=True)
        response_str = "{}"

    cleaned_response = _clean_json_response(response_str)
    try:
        tool_id_result = ToolIdentifierResponse.model_validate_json(cleaned_response)
        available_tool_names = {tool['name'] for tool in available_tools}
        required_tool_names = [name for name in tool_id_result.required_tools if name in available_tool_names]
        logger.info(f"Identified required tools: {required_tool_names}")
    except Exception as e:
        logger.error(f"Failed to parse Tool Identifier response: {e}. Assuming no tools. Raw: '{response_str}'")
        required_tool_names = []
        
    if not required_tool_names:
        logger.info("No valid tools required. Proceeding directly to synthesis.")
        return SynthesizeResponse(final_response_stream_url=f"/api/chat/stream/{request.message_id}")

    # --- 3. Parameter Extraction Step (Category: Tools) ---
    logger.info(f"Required tools identified: {required_tool_names}. Extracting parameters...")
    required_tool_definitions = [tool for tool in available_tools if tool.get("name") in required_tool_names]
    
    # --- FIXED: Format schemas string and inject into prompt ---
    tool_schemas_str = ""
    for td in required_tool_definitions:
        tool_schemas_str += f"- Tool: {td['name']}\n  Schema: {json.dumps(td.get('inputSchema', {}))}\n"
    
    param_ext_prompt = prompts.PARAMETER_EXTRACTOR_SYSTEM_PROMPT.format(
        tool_schemas=tool_schemas_str
    )
    
    # FIX: Use full_history_dicts
    response_str = await llm_manager.call_llm(tools_config, param_ext_prompt, full_history_dicts, json_mode=True)

    cleaned_response = _clean_json_response(response_str)
    try:
        from app.schemas.chat_schemas import ParameterExtractorResult
        param_ext_result = ParameterExtractorResult.model_validate_json(cleaned_response)
        
        # --- SAFETY CHECK: Filter out hallucinations ---
        # Remove any extracted parameters for tools NOT in the required list
        param_ext_result.extracted_parameters = {
            k: v for k, v in param_ext_result.extracted_parameters.items() 
            if k in required_tool_names
        }
        # Remove missing parameter flags for tools NOT in the required list
        param_ext_result.missing_parameters = [
            m for m in param_ext_result.missing_parameters 
            if m.tool in required_tool_names
        ]
        
    except Exception as e:
        logger.error(f"Failed to parse Parameter Extractor response: {e}. Stopping. Raw: '{response_str}'")
        return StopResponse(reason="Internal error in Parameter Extractor response parsing.")

    if param_ext_result.missing_parameters:
        logger.info("Missing parameters identified. Generating clarification question.")
        output_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT)
        clarifier_prompt = prompts.CLARIFIER_SYSTEM_PROMPT.format(bot_name=bot.name, bot_personality=bot.personality)
        technical_question = param_ext_result.clarification_question or "I need more information."
        clarifier_messages = [{"role": "user", "content": f"Rephrase this technical question: {technical_question}"}]
        user_facing_question = await llm_manager.call_llm(output_config, clarifier_prompt, clarifier_messages)
        return ClarifyResponse(message=user_facing_question)

    # --- 4. Planning Step (Category: Tools) ---
    logger.info("All required parameters are present. Proceeding to planning.")
    
    # --- BUG FIX: Create string of allowed tools and clean input ---
    allowed_tools_str = ", ".join(required_tool_names)
    clean_params_input = json.dumps(param_ext_result.extracted_parameters)

    # Inject Playbook content AND Allowed Tools into Planner prompt
    planner_prompt = prompts.PLANNER_SYSTEM_PROMPT.format(
        ace_playbook=playbook_content,
        allowed_tools=allowed_tools_str
    )
    
    planner_messages = [{"role": "user", "content": f"Create a plan for these tools and parameters: {clean_params_input}"}]
    
    response_str = await llm_manager.call_llm(tools_config, planner_prompt, planner_messages, json_mode=True)

    cleaned_response = _clean_json_response(response_str)
    try:
        plan_result = PlannerResult.model_validate_json(cleaned_response)
        if not plan_result.plan:
            raise ValueError("Planner returned an empty plan.")
    except Exception as e:
        logger.error(f"Failed to parse Planner response or plan is empty: {e}. Stopping. Raw: '{response_str}'")
        return StopResponse(reason="Failed to create an execution plan.")

    # --- 4.5. Plan Validation Step (Internal Logic) ---
    logger.info("Validating generated plan against identified tools...")
    identified_tool_names_set = set(required_tool_names)
    planned_tool_names = {step.tool_name for step in plan_result.plan}

    # Check if all tools in the plan were actually identified as required.
    if not planned_tool_names.issubset(identified_tool_names_set):
        invalid_tools = planned_tool_names - identified_tool_names_set
        error_msg = f"Planner hallucinated invalid tools: {list(invalid_tools)}. These were not identified in the initial step. Stopping execution."
        logger.error(error_msg)
        return StopResponse(reason="Internal error: Failed to execute the request due to an invalid processing plan.")
    
    logger.info("Plan validation successful.")

    # --- 5. Acknowledgement Step (Category: Output Client) ---
    logger.info("Plan created successfully. Generating acknowledgement message.")
    output_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT)
    ack_prompt = prompts.ACKNOWLEDGER_SYSTEM_PROMPT.format(bot_personality=bot.personality)
    ack_messages = [{"role": "user", "content": "The user's request requires tool execution. Generate an acknowledgement."}]
    ack_message = await llm_manager.call_llm(output_config, ack_prompt, ack_messages)

    return AcknowledgeAndExecuteResponse(
        acknowledgement_message=ack_message,
        final_response_stream_url=f"/api/chat/stream/{request.message_id}",
        plan=plan_result,
        tool_definitions=required_tool_definitions
    )

# --- Synthesis Phase Router ---

async def run_synthesis_phase(
    bot: sql_models.Bot,
    global_settings: sql_models.GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Routes to the appropriate synthesizer based on whether tools were executed.
    This is the new entry point for the final response generation phase.
    """
    # Load Playbook content for Synthesis
    playbook_content = _load_bot_playbook_content(bot.id)

    if tool_results:
        logger.info("Tool results are present. Routing to Tool Result Synthesizer.")
        async for chunk in synthesizer.run_tool_result_synthesizer(
            bot=bot,
            global_settings=global_settings,
            history=history,
            tool_results=tool_results,
            playbook_content=playbook_content # Pass playbook
        ):
            yield chunk
    else:
        logger.info("No tool results. Routing to standard conversational Synthesizer.")
        async for chunk in synthesizer.run_synthesizer(
            bot=bot,
            global_settings=global_settings,
            history=history,
            tool_results=tool_results,
            playbook_content=playbook_content # Pass playbook
        ):
            yield chunk


# --- REFACTORED: Tool Discovery with MCP-Use (Fault Tolerant) ---

async def get_available_tools_for_bot(db: Session, bot_id: int) -> List[Dict[str, Any]]:
    """
    Fetches available tools using MCP-Use.
    Iterates over each server individually to isolate failures.
    Includes retry logic for unstable SSE connections.
    """
    logger.info(f"Fetching available tools for bot_id: {bot_id} (via MCP-Use)")
    mcp_servers = crud_mcp.get_mcp_servers_for_bot(db, bot_id=bot_id)
    if not mcp_servers:
        return []

    all_tools = []
    
    # Iterate over each server individually to prevent one failure from blocking all tools
    for server in mcp_servers:
        base_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
        server_key = f"server_{server.id}"
        
        # Create a dedicated configuration for this single server
        single_server_config = {
            "mcpServers": {
                server_key: {
                    "transport": "sse",
                    "url": base_url,
                }
            }
        }
        
        # --- RETRY LOGIC FOR DISCOVERY ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Instantiate a fresh client for this server
                client = MCPClient(single_server_config)
                await client.create_all_sessions()
                
                session = client.get_session(server_key)
                if session:
                    tools = await session.list_tools()
                    for tool in tools:
                        all_tools.append({
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema or {},
                            "server_id": server.id 
                        })
                    logger.info(f"Successfully discovered {len(tools)} tools from server {server.name}")
                    
                    # Explicit cleanup (Best effort if supported by library or context)
                    # Currently mcp-use doesn't expose a clean way to close 'client' 
                    # but we can try closing the session if accessible.
                    # Assuming Garbage Collection handles it, but connection drop issues might persist.
                    # Success -> Break retry loop
                    break
                else:
                    logger.warning(f"No session created for server {server.name}")
                    break # No session means config error usually, don't retry network

            except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as net_err:
                logger.warning(f"Network error discovering tools on {server.name} (Attempt {attempt+1}/{max_retries}): {net_err}")
                if attempt == max_retries - 1:
                    logger.error(f"Final failure for server {server.name}: {net_err}")
                else:
                    await asyncio.sleep(0.5) # Brief backoff
            except Exception as e:
                # Log error but CONTINUE to next server (do not break global loop)
                logger.error(f"Discovery failed for server {server.name} ({base_url}): {e}")
                break
    
    return all_tools


# --- REFACTORED: Execution with MCP-Use ---

async def execute_tool_plan(
    db: Session, bot_id: int, plan_result: PlannerResult, tool_definitions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Executes the planned tools using MCP-Use.
    Includes retry logic for unstable SSE connections.
    """
    logger.info(f"Starting execution of plan for bot {bot_id} using MCP-Use")
    tool_execution_results = []
    
    # 1. Identify involved servers
    involved_server_ids = set()
    tool_map = {tool['name']: tool for tool in tool_definitions}
    
    for step in plan_result.plan:
        tool_def = tool_map.get(step.tool_name)
        if tool_def and 'server_id' in tool_def:
            involved_server_ids.add(tool_def['server_id'])
    
    # 2. Build MCP Config for involved servers
    mcp_config = {"mcpServers": {}}
    
    for server_id in involved_server_ids:
        # Retrieve server details (using associations ensures we only get active/associated ones)
        association = crud_mcp.get_association(db, bot_id=bot_id, mcp_server_id=server_id)
        if association and association.mcp_server:
            server = association.mcp_server
            base_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
            mcp_config["mcpServers"][f"server_{server.id}"] = {
                "transport": "sse",
                "url": base_url,
            }

    if not mcp_config["mcpServers"]:
        logger.error("No valid servers found for the plan. Skipping execution.")
        return []

    # 3. Execute Steps with Retry Logic
    max_retries = 3
    
    # We try to execute the WHOLE plan. If a connection drops, we recreate the client.
    # Note: If a tool has side effects, retrying might be dangerous. 
    # But here we handle connection errors mainly.
    
    client = None
    try:
        # Initial Client Creation
        client = MCPClient(mcp_config)
        await client.create_all_sessions()
        
        for step in sorted(plan_result.plan, key=lambda x: x.step):
            tool_name = step.tool_name
            tool_def = tool_map.get(tool_name)
            
            if not tool_def:
                logger.error(f"Definition not found for tool {tool_name}")
                tool_execution_results.append({"tool_name": tool_name, "result": {"error": "Tool definition not found"}})
                continue

            server_id = tool_def.get('server_id')
            server_key = f"server_{server_id}"
            
            logger.info(f"Executing step {step.step}: calling tool '{tool_name}' on {server_key}")

            # RETRY LOOP PER TOOL CALL
            tool_success = False
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    session = client.get_session(server_key)
                    if not session:
                        # Try to recreate sessions if lost
                        logger.warning(f"Session lost for {server_key}, attempting to reconnect...")
                        await client.create_all_sessions()
                        session = client.get_session(server_key)
                        
                    if not session:
                        raise Exception(f"No active session for {server_key}")

                    # CALL TOOL
                    result_obj = await session.call_tool(tool_name, step.arguments)
                    
                    # PROCESS RESULT
                    final_output = {}
                    content_list = []
                    
                    if hasattr(result_obj, 'content') and isinstance(result_obj.content, list):
                        for item in result_obj.content:
                            if hasattr(item, 'type') and hasattr(item, 'text') and item.type == 'text':
                                content_list.append(item.text)
                            elif hasattr(item, 'type') and item.type == 'image':
                                 content_list.append(f"[Image Data: {item.mimeType}]")
                            else:
                                content_list.append(str(item))
                        
                        final_output = {
                            "text_content": "\n".join(content_list), 
                            "raw_mcp_content": [c.model_dump() if hasattr(c, 'model_dump') else str(c) for c in result_obj.content]
                        }
                    else:
                        final_output = {"result": str(result_obj)}

                    if getattr(result_obj, "isError", False):
                         final_output["is_error"] = True

                    tool_execution_results.append({"tool_name": tool_name, "result": final_output})
                    tool_success = True
                    break # Success

                except (httpx.RemoteProtocolError, httpx.ReadTimeout) as net_err:
                    last_error = net_err
                    logger.warning(f"Network error executing {tool_name} (Attempt {attempt+1}/{max_retries}): {net_err}")
                    # Recreate Client on network failure to ensure fresh sockets
                    try:
                        client = MCPClient(mcp_config)
                        await client.create_all_sessions()
                    except:
                        pass
                    await asyncio.sleep(0.5)

                except Exception as e:
                    last_error = e
                    logger.error(f"Error executing tool {tool_name}: {e}")
                    # Application error (not network), do not retry
                    break
            
            if not tool_success:
                 tool_execution_results.append({"tool_name": tool_name, "result": {"error": str(last_error)}})

    except Exception as e:
         logger.error(f"Fatal error in MCP execution loop: {e}", exc_info=True)
    
    return tool_execution_results