import logging
from typing import Union, List, Dict, Any, Optional, AsyncGenerator
import asyncio
import json
import os
import re
from datetime import datetime, timezone # NOUVEAU

from pydantic import BaseModel

# --- NEW: MCP-Use Import & HTTPX for Exceptions ---
from mcp_use import MCPClient
import httpx
# ---------------------------

from sqlalchemy.orm import Session

from app.core import llm_manager
# NOUVEAU: Import du MemoryManager
from app.core.memory_manager import MemoryManager

from app.core.agents import prompts, synthesizer

# Schema Imports
from app.schemas.chat_schemas import (
    ProcessMessageRequest,
    StopResponse,
    ClarifyResponse,
    AcknowledgeAndExecuteResponse,
    SynthesizeResponse,
    PlannerResult,
    ChatMessage
)

# Database CRUD Imports
from app.database import crud_bots, crud_mcp, crud_settings, sql_models

# ACE Framework Import
try:
    from ace.playbook import Playbook
    ACE_INSTALLED = True
except ImportError:
    ACE_INSTALLED = False
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
    """
    if not raw_response:
        return "{}"
    
    cleaned = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL)
    
    start_obj = cleaned.find("{")
    start_arr = cleaned.find("[")
    
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
    if not ACE_INSTALLED:
        return ""
    playbook_path = f"/app/data/playbooks/{bot_id}.json"
    if not os.path.exists(playbook_path):
        return ""
    try:
        playbook = Playbook.from_file(playbook_path)
        return playbook.as_prompt()
    except Exception as e:
        logger.error(f"Failed to load ACE playbook for bot {bot_id}: {e}")
        return ""

def _get_current_time_str() -> str:
    """Returns the current UTC time formatted for prompt injection."""
    return datetime.now(timezone.utc).strftime("%A, %B %d, %Y, %H:%M UTC")

def _format_message_with_context(content: str, user_name: str, user_id: str, timestamp_str: str) -> str:
    """Formats a message to include time and strict user identification."""
    return f"[{timestamp_str}] {user_name} (ID: {user_id}): {content}"

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
    
    # Calculate timestamps once for consistency
    current_time_str = _get_current_time_str()

    # 1. LOAD PLAYBOOK
    playbook_content = _load_bot_playbook_content(bot.id)

    # 2. MEMORY RETRIEVAL (NEW)
    # Initialize Mem0 for this bot
    memory_client = MemoryManager.get_memory_client(bot, global_settings)
    # Search for relevant memories based on the user's current message
    # We use a unique ID combining Bot + Discord User ID to isolate memories
    user_mem_id = f"{request.user_id}" 
    relevant_memories = MemoryManager.get_memories(memory_client, user_id=user_mem_id, query=request.message_content)
    
    if relevant_memories:
        logger.info(f"Found relevant memories for user {request.user_id}: {relevant_memories[:50]}...")
    else:
        logger.info("No relevant long-term memories found.")

    # 3. CONSTRUCT HISTORY WITH TIME AWARENESS
    
    # Format the current message with explicit Metadata (Time + User ID)
    # This ensures the LLM knows EXACTLY who is speaking and when.
    formatted_current_content = _format_message_with_context(
        content=request.message_content,
        user_name=request.user_display_name,
        user_id=str(request.user_id),
        timestamp_str=current_time_str
    )
    
    # Inject Memory Context if available
    final_message_content = formatted_current_content
    if relevant_memories:
         final_message_content = f"""[CONTEXTUAL MEMORY START]
The following facts are recalled from previous conversations with this user:
{relevant_memories}
[CONTEXTUAL MEMORY END]

{formatted_current_content}"""

    # Create the proper ChatMessage object
    current_message = ChatMessage(
        role="user", 
        content=final_message_content, 
        name=request.user_display_name
    )
    
    full_history_dicts = [msg.model_dump() for msg in request.history]
    full_history_dicts.append(current_message.model_dump())

    # --- MEMORY UPDATE (FIRE AND FORGET) ---
    # We schedule the memory update to run in background so we don't block the response
    # Mem0 will extract facts from "request.message_content" (original)
    asyncio.create_task(
        MemoryManager.add_interaction(
            memory_client, 
            user_id=user_mem_id, 
            user_message=request.message_content, 
            bot_response="" # We add response later if needed, mostly user facts matter
        )
    )

    # --- 1. Gatekeeper Step ---
    bypass_gatekeeper = request.is_direct_message or request.is_direct_mention
    if not bypass_gatekeeper:
        logger.info("Running Gatekeeper...")
        decisional_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_DECISIONAL)
        
        # Inject Current Time into Gatekeeper Prompt
        gatekeeper_prompt = prompts.GATEKEEPER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            current_time=current_time_str
        )
        response_str = await llm_manager.call_llm(decisional_config, gatekeeper_prompt, full_history_dicts, json_mode=True)
        
        cleaned_response = _clean_json_response(response_str)
        try:
            gatekeeper_decision = GatekeeperResponse.model_validate_json(cleaned_response)
            if not gatekeeper_decision.should_respond:
                return StopResponse(reason=gatekeeper_decision.reason)
        except Exception as e:
            logger.error(f"Gatekeeper error: {e}")
            return StopResponse(reason="Gatekeeper error")

    # --- 2. Tool Identification Step ---
    available_tools = await get_available_tools_for_bot(db, bot.id)
    tools_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_TOOLS)
    
    tools_entries = []
    for tool in available_tools:
        name = tool.get('name', 'unknown')
        desc = tool.get('description', 'No description')
        input_schema = tool.get('inputSchema', {})
        properties = input_schema.get('properties', {})
        arg_keys = list(properties.keys()) if properties else []
        args_str = ", ".join(arg_keys) if arg_keys else "None"
        tools_entries.append(f"- {name}: {desc} (Arguments: {args_str})")
        
    tools_list_str = "\n".join(tools_entries)
    
    # Inject Current Time into Tool Identifier Prompt
    tool_id_prompt = prompts.TOOL_IDENTIFIER_SYSTEM_PROMPT.format(
        tools_list=tools_list_str,
        ace_playbook=playbook_content,
        current_time=current_time_str
    )
    
    try:
        response_str = await llm_manager.call_llm(tools_config, tool_id_prompt, full_history_dicts, json_mode=True)
    except Exception as llm_error:
        logger.error(f"Tool Identifier error: {llm_error}")
        response_str = "{}"

    cleaned_response = _clean_json_response(response_str)
    try:
        tool_id_result = ToolIdentifierResponse.model_validate_json(cleaned_response)
        available_tool_names = {tool['name'] for tool in available_tools}
        required_tool_names = [name for name in tool_id_result.required_tools if name in available_tool_names]
    except Exception:
        required_tool_names = []
        
    if not required_tool_names:
        return SynthesizeResponse(final_response_stream_url=f"/api/chat/stream/{request.message_id}")

    # --- 3. Parameter Extraction ---
    required_tool_definitions = [tool for tool in available_tools if tool.get("name") in required_tool_names]
    tool_schemas_str = ""
    for td in required_tool_definitions:
        tool_schemas_str += f"- Tool: {td['name']}\n  Schema: {json.dumps(td.get('inputSchema', {}))}\n"
    
    # Param Extractor prompt doesn't strictly need time, but we use the standard helper anyway
    param_ext_prompt = prompts.PARAMETER_EXTRACTOR_SYSTEM_PROMPT.format(tool_schemas=tool_schemas_str)
    response_str = await llm_manager.call_llm(tools_config, param_ext_prompt, full_history_dicts, json_mode=True)

    cleaned_response = _clean_json_response(response_str)
    try:
        from app.schemas.chat_schemas import ParameterExtractorResult
        param_ext_result = ParameterExtractorResult.model_validate_json(cleaned_response)
        
        # Filter hallucinations
        param_ext_result.extracted_parameters = {
            k: v for k, v in param_ext_result.extracted_parameters.items() 
            if k in required_tool_names
        }
        param_ext_result.missing_parameters = [
            m for m in param_ext_result.missing_parameters 
            if m.tool in required_tool_names
        ]
    except Exception as e:
        return StopResponse(reason="Parameter extraction error")

    if param_ext_result.missing_parameters:
        output_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT)
        clarifier_prompt = prompts.CLARIFIER_SYSTEM_PROMPT.format(bot_name=bot.name, bot_personality=bot.personality)
        technical_question = param_ext_result.clarification_question or "I need more information."
        clarifier_messages = [{"role": "user", "content": f"Rephrase this technical question: {technical_question}"}]
        user_facing_question = await llm_manager.call_llm(output_config, clarifier_prompt, clarifier_messages)
        return ClarifyResponse(message=user_facing_question)

    # --- 4. Planning ---
    allowed_tools_str = ", ".join(required_tool_names)
    clean_params_input = json.dumps(param_ext_result.extracted_parameters)

    # Inject Current Time into Planner Prompt
    planner_prompt = prompts.PLANNER_SYSTEM_PROMPT.format(
        ace_playbook=playbook_content,
        allowed_tools=allowed_tools_str,
        current_time=current_time_str
    )
    planner_messages = [{"role": "user", "content": f"Create a plan for these tools and parameters: {clean_params_input}"}]
    response_str = await llm_manager.call_llm(tools_config, planner_prompt, planner_messages, json_mode=True)

    cleaned_response = _clean_json_response(response_str)
    try:
        plan_result = PlannerResult.model_validate_json(cleaned_response)
        if not plan_result.plan:
            raise ValueError("Empty plan")
    except Exception:
        return StopResponse(reason="Planning error")

    # --- 4.5 Validation ---
    identified_tool_names_set = set(required_tool_names)
    planned_tool_names = {step.tool_name for step in plan_result.plan}
    if not planned_tool_names.issubset(identified_tool_names_set):
        return StopResponse(reason="Planner hallucinated tools")

    # --- 5. Acknowledgement ---
    output_config = llm_manager.resolve_llm_config(bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT)
    ack_prompt = prompts.ACKNOWLEDGER_SYSTEM_PROMPT.format(bot_personality=bot.personality)
    ack_messages = [{"role": "user", "content": "Generate an acknowledgement."}]
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
    
    playbook_content = _load_bot_playbook_content(bot.id)
    # Get current time for the synthesizer prompt
    current_time_str = _get_current_time_str()

    if tool_results:
        async for chunk in synthesizer.run_tool_result_synthesizer(
            bot=bot,
            global_settings=global_settings,
            history=history,
            tool_results=tool_results,
            playbook_content=playbook_content,
            current_time=current_time_str # Pass time to synthesizer
        ):
            yield chunk
    else:
        async for chunk in synthesizer.run_synthesizer(
            bot=bot,
            global_settings=global_settings,
            history=history,
            tool_results=tool_results,
            playbook_content=playbook_content,
            current_time=current_time_str # Pass time to synthesizer
        ):
            yield chunk

# --- Tool Discovery & Execution (Unchanged MCP Logic) ---

async def get_available_tools_for_bot(db: Session, bot_id: int) -> List[Dict[str, Any]]:
    mcp_servers = crud_mcp.get_mcp_servers_for_bot(db, bot_id=bot_id)
    if not mcp_servers:
        return []

    all_tools = []
    for server in mcp_servers:
        base_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
        server_key = f"server_{server.id}"
        single_server_config = {"mcpServers": {server_key: {"transport": "sse", "url": base_url}}}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
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
                    break
            except Exception:
                if attempt == max_retries - 1:
                    logger.error(f"Discovery failed for server {server.name}")
                await asyncio.sleep(0.5)
    return all_tools


async def execute_tool_plan(
    db: Session, bot_id: int, plan_result: PlannerResult, tool_definitions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    
    tool_execution_results = []
    involved_server_ids = set()
    tool_map = {tool['name']: tool for tool in tool_definitions}
    
    for step in plan_result.plan:
        tool_def = tool_map.get(step.tool_name)
        if tool_def and 'server_id' in tool_def:
            involved_server_ids.add(tool_def['server_id'])
    
    mcp_config = {"mcpServers": {}}
    for server_id in involved_server_ids:
        association = crud_mcp.get_association(db, bot_id=bot_id, mcp_server_id=server_id)
        if association and association.mcp_server:
            server = association.mcp_server
            base_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
            mcp_config["mcpServers"][f"server_{server.id}"] = {"transport": "sse", "url": base_url}

    if not mcp_config["mcpServers"]:
        return []

    max_retries = 3
    client = None
    try:
        client = MCPClient(mcp_config)
        await client.create_all_sessions()
        
        for step in sorted(plan_result.plan, key=lambda x: x.step):
            tool_name = step.tool_name
            tool_def = tool_map.get(tool_name)
            if not tool_def:
                continue

            server_id = tool_def.get('server_id')
            server_key = f"server_{server_id}"
            
            tool_success = False
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    session = client.get_session(server_key)
                    if not session:
                        await client.create_all_sessions()
                        session = client.get_session(server_key)
                    
                    result_obj = await session.call_tool(tool_name, step.arguments)
                    
                    final_output = {}
                    content_list = []
                    if hasattr(result_obj, 'content') and isinstance(result_obj.content, list):
                        for item in result_obj.content:
                            if hasattr(item, 'type') and hasattr(item, 'text') and item.type == 'text':
                                content_list.append(item.text)
                            else:
                                content_list.append(str(item))
                        final_output = {"text_content": "\n".join(content_list)}
                    else:
                        final_output = {"result": str(result_obj)}

                    if getattr(result_obj, "isError", False):
                         final_output["is_error"] = True

                    tool_execution_results.append({"tool_name": tool_name, "result": final_output})
                    tool_success = True
                    break

                except (httpx.RemoteProtocolError, httpx.ReadTimeout) as net_err:
                    last_error = net_err
                    try:
                        client = MCPClient(mcp_config)
                        await client.create_all_sessions()
                    except: pass
                    await asyncio.sleep(0.5)
                except Exception as e:
                    last_error = e
                    break
            
            if not tool_success:
                 tool_execution_results.append({"tool_name": tool_name, "result": {"error": str(last_error)}})

    except Exception as e:
         logger.error(f"Fatal error in MCP execution: {e}")
    
    return tool_execution_results