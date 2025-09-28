import logging
from typing import Union, List, Dict, Any, Optional
import httpx
import asyncio
import json

from sqlalchemy.orm import Session

# Agent Imports
from app.core.agents import (
    gatekeeper,
    tool_identifier,
    parameter_extractor,
    clarifier,
    planner,
    acknowledger
)

# Schema Imports
from app.schemas.chat_schemas import (
    ProcessMessageRequest,
    StopResponse,
    ClarifyResponse,
    AcknowledgeAndExecuteResponse,
    SynthesizeResponse,
    PlannerResult
)

# Database CRUD Imports
from app.database import crud_bots, crud_mcp

logger = logging.getLogger(__name__)


async def get_available_tools_for_bot(db: Session, bot_id: int) -> List[Dict[str, Any]]:
    """
    Fetches all available tools for a bot by querying its associated MCP servers.
    Each tool dictionary is augmented with a 'server_id' key.
    """
    logger.info(f"Fetching available tools for bot_id: {bot_id}")
    mcp_servers = crud_mcp.get_mcp_servers_for_bot(db, bot_id=bot_id)
    if not mcp_servers:
        logger.info("No MCP servers are configured for this bot.")
        return []

    all_tools = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for server in mcp_servers:
            host = server.host
            if not host.startswith(('http://', 'https://')):
                host = f"http://{host}"

            rpc_path = server.rpc_endpoint_path
            if not rpc_path.startswith("/"):
                rpc_path = "/" + rpc_path
            
            server_url = f"{host}:{server.port}{rpc_path}"
            tasks.append(_fetch_tools_from_mcp(client, server_url, server.id))
        
        results = await asyncio.gather(*tasks)
        for server_id, tool_list in results:
            if tool_list:
                for tool in tool_list:
                    tool['server_id'] = server_id
                all_tools.extend(tool_list)
    
    logger.info(f"Found a total of {len(all_tools)} tools for bot_id: {bot_id}")
    return all_tools

async def _fetch_tools_from_mcp(client: httpx.AsyncClient, server_url: str, server_id: int) -> tuple[int, Optional[List[Dict[str, Any]]]]:
    """Helper to fetch tools from a single MCP server."""
    try:
        payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
        response = await client.post(server_url, json=payload, timeout=10.0)
        response.raise_for_status()
        
        json_response = response.json()
        if json_response.get("error"):
            logger.error(f"MCP server at {server_url} returned an error: {json_response['error']}")
            return server_id, None
        
        return server_id, json_response.get("result", {}).get("tools", [])

    except httpx.RequestError as e:
        logger.error(f"Failed to connect to MCP server at {server_url}: {e}")
        return server_id, None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching tools from {server_url}: {e}", exc_info=True)
        return server_id, None


async def process_user_message(
    db: Session,
    request: ProcessMessageRequest
) -> Union[StopResponse, ClarifyResponse, AcknowledgeAndExecuteResponse, SynthesizeResponse]:
    """
    Orchestrates the agent chain to process a user's message.
    """
    logger.info(f"Orchestrator starting for message {request.message_id} in channel {request.channel_id}")

    bot = crud_bots.get_bot(db=db, bot_id=request.bot_id)
    if not bot:
        return StopResponse(reason=f"Bot with ID {request.bot_id} not found.")

    # --- MODIFICATION: Check for is_direct_message OR is_direct_mention to bypass Gatekeeper ---
    is_direct_message = request.is_direct_message
    is_direct_mention = request.is_direct_mention
    bypass_gatekeeper = is_direct_message or is_direct_mention

    if not bypass_gatekeeper:
        logger.info("Running Gatekeeper for ambient message...")
        gatekeeper_decision = await gatekeeper.run_gatekeeper(
            bot_name=bot.name,
            history=request.history
        )
        if not gatekeeper_decision.should_respond:
            logger.info(f"Gatekeeper decided not to respond. Reason: {gatekeeper_decision.reason}. Stopping processing.")
            return StopResponse(reason=gatekeeper_decision.reason)
        logger.info("Gatekeeper approved the response. Proceeding.")
    else:
        if is_direct_message:
            logger.info("Bypassing Gatekeeper because this is a direct message.")
        if is_direct_mention:
            logger.info("Bypassing Gatekeeper because this is a direct mention.")
    # --- END MODIFICATION ---
    
    available_tools = await get_available_tools_for_bot(db, bot.id)

    tool_id_result = await tool_identifier.run_tool_identifier(request.history, available_tools)

    # --- FIX: Validate and filter hallucinated tool names ---
    available_tool_names = {tool['name'] for tool in available_tools}
    validated_tool_names = [
        name for name in tool_id_result.required_tools if name in available_tool_names
    ]

    if tool_id_result.required_tools and not validated_tool_names:
        logger.warning(
            f"Tool Identifier hallucinated tool(s): {tool_id_result.required_tools}. "
            f"None of them are in the available list: {available_tool_names}. Proceeding to synthesis."
        )
    
    if not validated_tool_names:
        logger.info("No valid tools required. Proceeding directly to synthesis.")
        return SynthesizeResponse(final_response_stream_url=f"/api/chat/stream/{request.message_id}")

    required_tool_names = validated_tool_names
    # --- END FIX ---

    required_tool_definitions = [
        tool for tool in available_tools if tool.get("name") in required_tool_names
    ]

    param_ext_result = await parameter_extractor.run_parameter_extractor(
        request.history,
        required_tool_definitions
    )

    if param_ext_result.missing_parameters:
        logger.info("Missing parameters identified. Generating clarification question.")
        
        technical_question = param_ext_result.clarification_question or "I need more information."
        
        user_facing_question = await clarifier.run_clarifier(
            technical_question=technical_question,
            bot_personality=bot.personality,
            bot_name=bot.name,
            history=request.history
        )
        return ClarifyResponse(message=user_facing_question)

    extracted_tool_names = set(param_ext_result.extracted_parameters.keys())
    required_tool_names_set = set(required_tool_names)

    if extracted_tool_names != required_tool_names_set:
        logger.error(
            f"Mismatch between required tools and extracted parameters. "
            f"Required: {required_tool_names_set}, "
            f"Extracted for: {extracted_tool_names}. "
            f"Stopping execution to prevent planner failure."
        )
        return StopResponse(reason="Internal error: failed to consistently extract all required tool parameters.")

    logger.info("All required parameters are present and validated. Proceeding to planning.")

    plan_result = await planner.run_planner(request.history, param_ext_result)

    if not plan_result.plan:
        logger.error("Parameter extraction succeeded, but Planner failed to create a plan.")
        return StopResponse(reason="Failed to create an execution plan.")

    logger.info("Plan created successfully. Generating acknowledgement message.")
    ack_message = await acknowledger.run_acknowledger(
        plan=plan_result,
        bot_personality=bot.personality,
        bot_name=bot.name,
        history=request.history
    )
    
    # === MODIFICATION START: Populate the response with plan details for Redis ===
    return AcknowledgeAndExecuteResponse(
        acknowledgement_message=ack_message,
        final_response_stream_url=f"/api/chat/stream/{request.message_id}",
        plan=plan_result,
        tool_definitions=required_tool_definitions
    )
    # === MODIFICATION END ===

async def execute_tool_plan(
    db: Session, bot_id: int, plan_result: PlannerResult, tool_definitions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Executes a plan generated by the Planner agent.
    It retrieves the bot-specific configuration for each tool before calling it.
    """
    logger.info(f"Starting execution of plan for bot {bot_id}")
    step_results = {}
    tool_execution_results = []

    tool_map = {tool['name']: tool for tool in tool_definitions}

    async with httpx.AsyncClient() as client:
        for step in sorted(plan_result.plan, key=lambda x: x.step):
            tool_name = step.tool_name
            logger.info(f"Executing step {step.step}: calling tool '{tool_name}'")

            # TODO: Implement dependency resolution for arguments.

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
            
            logger.info(f"Tool '{tool_name}' will be called with bot-specific config: {tool_config}")

            host = server.host
            if not host.startswith(('http://', 'https://')):
                host = f"http://{host}"
            rpc_path = server.rpc_endpoint_path
            if not rpc_path.startswith("/"):
                rpc_path = "/" + rpc_path
            server_url = f"{host}:{server.port}{rpc_path}"

            payload = {
                "jsonrpc": "2.0", "id": step.step, "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": step.arguments,
                    "configuration": tool_config
                }
            }

            try:
                response = await client.post(server_url, json=payload, timeout=30.0)
                response.raise_for_status()
                json_response = response.json()

                if json_response.get("error"):
                    result = {"error": json_response["error"]}
                    logger.error(f"Error from tool '{tool_name}': {result}")
                else:
                    result = json_response.get("result", {})
                    logger.info(f"Success from tool '{tool_name}'")
                
                step_results[step.step] = result
                tool_execution_results.append({"tool_name": tool_name, "result": result})

            except httpx.RequestError as e:
                logger.error(f"RequestError calling tool '{tool_name}': {e}")
            except Exception as e:
                logger.error(f"Exception calling tool '{tool_name}': {e}", exc_info=True)

    return tool_execution_results