import logging
from typing import Union, List, Dict, Any, Optional, AsyncGenerator
import httpx
import asyncio
import json
import os # MODIFIED: Added os for file path handling
from pydantic import BaseModel, Field

# NEW: Add websockets for handling MCP streams
import websockets

from sqlalchemy.orm import Session

# NEW: Import the LLM manager and prompts
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
)

# Database CRUD Imports
from app.database import crud_bots, crud_mcp, crud_settings, sql_models

# --- MODIFICATION START: ACE Framework Import ---
try:
    from ace.playbook import Playbook
    ACE_INSTALLED = True
except ImportError:
    ACE_INSTALLED = False
    # Dummy class to prevent runtime errors if ACE is not present
    class Playbook: pass
# --- MODIFICATION END ---

logger = logging.getLogger(__name__)

# --- Internal Pydantic models for response validation ---

class GatekeeperResponse(BaseModel):
    should_respond: bool
    reason: str

class ToolIdentifierResponse(BaseModel):
    required_tools: List[str]

# --- Helper for Playbook Loading ---

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
    
    # MODIFICATION: Load Playbook content early for use in Planner
    playbook_content = _load_bot_playbook_content(bot.id)

    # --- 1. Gatekeeper Step (Category: Decisional) ---
    bypass_gatekeeper = request.is_direct_message or request.is_direct_mention
    if not bypass_gatekeeper:
        logger.info("Running Gatekeeper for ambient message...")
        
        # Resolve config and call LLM
        decisional_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_DECISIONAL)
        gatekeeper_prompt = prompts.GATEKEEPER_SYSTEM_PROMPT.format(bot_name=bot.name)
        response_str = await llm_manager.call_llm(decisional_config, gatekeeper_prompt, request.history, json_mode=True)
        
        try:
            gatekeeper_decision = GatekeeperResponse.model_validate_json(response_str)
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
    logger.debug(f"Available tools for bot {bot.id}: {[t['name'] for t in available_tools]}")
    
    tools_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_TOOLS)
    logger.info(f"Tool Identifier using model: {tools_config.model_name} at {tools_config.server_url}")

    tools_list_str = "\n".join([f"- {tool['name']}: {tool['description']}" for tool in available_tools])
    tool_id_prompt = prompts.TOOL_IDENTIFIER_SYSTEM_PROMPT.format(tools_list=tools_list_str)
    
    logger.info("Calling LLM for Tool Identifier...")
    try:
        response_str = await llm_manager.call_llm(tools_config, tool_id_prompt, request.history, json_mode=True)
        logger.info("LLM Response received for Tool Identifier.")
        logger.debug(f"Raw Tool Identifier Response: {response_str}")
    except Exception as llm_error:
        logger.error(f"CRITICAL ERROR during Tool Identifier LLM call: {llm_error}", exc_info=True)
        # Fail safe to allow flow to continue if possible, or re-raise
        # For now, let's treat it as an empty response (no tools) to unblock the bot
        response_str = "{}"

    try:
        tool_id_result = ToolIdentifierResponse.model_validate_json(response_str)
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
    
    param_ext_prompt = prompts.PARAMETER_EXTRACTOR_SYSTEM_PROMPT # No formatting needed
    # This is a complex task, so we continue to use the Tools category config
    response_str = await llm_manager.call_llm(tools_config, param_ext_prompt, request.history, json_mode=True)

    try:
        from app.schemas.chat_schemas import ParameterExtractorResult
        param_ext_result = ParameterExtractorResult.model_validate_json(response_str)
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
    
    # MODIFICATION: Inject Playbook content into Planner prompt
    planner_prompt = prompts.PLANNER_SYSTEM_PROMPT.format(ace_playbook=playbook_content)
    
    planner_messages = [{"role": "user", "content": f"Create a plan for these tools and parameters: {param_ext_result.model_dump_json()}"}]
    response_str = await llm_manager.call_llm(tools_config, planner_prompt, planner_messages, json_mode=True)

    try:
        plan_result = PlannerResult.model_validate_json(response_str)
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

# --- NEW Synthesis Phase Router ---

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
    # MODIFICATION: Load Playbook content for Synthesis
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


# --- Helper functions for tool discovery and execution ---

async def get_available_tools_for_bot(db: Session, bot_id: int) -> List[Dict[str, Any]]:
    logger.info(f"Fetching available tools for bot_id: {bot_id}")
    mcp_servers = crud_mcp.get_mcp_servers_for_bot(db, bot_id=bot_id)
    if not mcp_servers:
        return []

    all_tools = []
    async with httpx.AsyncClient() as client:
        tasks = [_fetch_tools_from_mcp(client, server) for server in mcp_servers]
        results = await asyncio.gather(*tasks)
        for server_id, tool_list in results:
            if tool_list:
                for tool in tool_list:
                    tool['server_id'] = server_id
                all_tools.extend(tool_list)
    return all_tools

async def _fetch_tools_from_mcp(client: httpx.AsyncClient, server) -> tuple[int, Optional[List[Dict[str, Any]]]]:
    host = server.host if server.host.startswith(('http://', 'https://')) else f"http://{server.host}"
    rpc_path = server.rpc_endpoint_path if server.rpc_endpoint_path.startswith("/") else f"/{server.rpc_endpoint_path}"
    server_url = f"{host}:{server.port}{rpc_path}"
    try:
        payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": server.id}
        response = await client.post(server_url, json=payload, timeout=10.0)
        response.raise_for_status()
        json_response = response.json()
        if "error" in json_response:
            logger.error(f"MCP server at {server_url} returned an error: {json_response['error']}")
            return server.id, None
        return server.id, json_response.get("result", {}).get("tools", [])
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to MCP server at {server_url}: {e}")
        return server.id, None
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching tools from {server_url}: {e}", exc_info=True)
        return server.id, None

# --- MODIFICATION START: Using keepalive instead of global timeouts ---
async def _handle_mcp_stream(websocket_url: str) -> Dict:
    """
    Connects to an MCP WebSocket stream with keepalive pings and waits for the final result.
    """
    try:
        # Use keepalive ping/pong to ensure connection is alive without a hard global timeout.
        async with websockets.connect(
            websocket_url,
            ping_interval=20, 
            ping_timeout=20
        ) as websocket:
            async for message_str in websocket:
                message_data = json.loads(message_str)
                params = message_data.get("params", {})
                # Check both chunk and end for a final result, similar to event_handler.py
                if message_data.get("method") in ("stream/chunk", "stream/end"):
                    if error_obj := params.get("error"):
                        return {"error": {"message": error_obj.get("message", "Unknown stream error")}}
                    elif result_obj := params.get("result"):
                        # This is the final result, wrap it for consistency
                        return {"result": result_obj}
    except Exception as e:
        logger.error(f"MCP stream connection error at {websocket_url}: {e}", exc_info=True)
        return {"error": {"message": f"Failed to handle the tool stream: {e}"}}
    # If the loop finishes without a result, it's an error
    logger.warning(f"Tool stream at {websocket_url} ended without a result or error message.")
    return {"error": {"message": "Tool stream ended without a result."}}
# --- MODIFICATION END ---


async def execute_tool_plan(
    db: Session, bot_id: int, plan_result: PlannerResult, tool_definitions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    logger.info(f"Starting execution of plan for bot {bot_id}")
    tool_execution_results = []
    tool_map = {tool['name']: tool for tool in tool_definitions}

    async with httpx.AsyncClient() as client:
        for step in sorted(plan_result.plan, key=lambda x: x.step):
            tool_name = step.tool_name
            logger.info(f"Executing step {step.step}: calling tool '{tool_name}'")

            tool_def = tool_map.get(tool_name)
            if not tool_def or 'server_id' not in tool_def:
                logger.error(f"Could not find a server_id for tool '{tool_name}'. Skipping.")
                continue
            
            server_id = tool_def['server_id']
            association = crud_mcp.get_association(db, bot_id=bot_id, mcp_server_id=server_id)
            if not association or not association.mcp_server:
                logger.error(f"Could not find MCP association for tool '{tool_name}' on server {server_id}")
                continue

            server = association.mcp_server
            tool_config = association.configuration or {}
            
            host = server.host if server.host.startswith(('http://', 'https://')) else f"http://{server.host}"
            rpc_path = server.rpc_endpoint_path if server.rpc_endpoint_path.startswith("/") else f"/{server.rpc_endpoint_path}"
            server_url = f"{host}:{server.port}{rpc_path}"

            payload = {
                "jsonrpc": "2.0", "id": step.step, "method": "tools/call",
                "params": {"name": tool_name, "arguments": step.arguments, "configuration": tool_config}
            }

            try:
                response = await client.post(server_url, json=payload, timeout=30.0)
                response.raise_for_status()
                json_response = response.json()
                
                final_result = None
                if "result" in json_response or "error" in json_response:
                    logger.info(f"Tool '{tool_name}' returned a direct response.")
                    final_result = {"error": json_response["error"]} if "error" in json_response else json_response.get("result", {})
                elif json_response.get("method") == "stream/start" and (ws_url := json_response.get("params", {}).get("ws_url")):
                    logger.info(f"Tool '{tool_name}' initiated a stream. Connecting to {ws_url}...")
                    stream_response = await _handle_mcp_stream(ws_url)
                    final_result = stream_response.get("result") or {"error": stream_response.get("error", {"message": "Unknown stream error"})}
                else:
                    logger.error(f"Tool '{tool_name}' returned an unknown response format: {json_response}")
                    final_result = {"error": "Invalid response format from tool server."}

                tool_execution_results.append({"tool_name": tool_name, "result": final_result})

            except Exception as e:
                logger.error(f"Exception calling tool '{tool_name}': {e}", exc_info=True)
                tool_execution_results.append({"tool_name": tool_name, "result": {"error": str(e)}})

    return tool_execution_results