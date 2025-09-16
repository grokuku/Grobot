####
# app/api/tools_api.py
####
import json
import httpx
import logging
import itertools
import asyncio
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import crud_bots
from app.database.sql_session import get_db
# Ensure sql_models is imported so SQLAlchemy can link relationships at startup
from app.database import sql_models

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Cache Implementation ---
# Cache for tool locations to speed up /call
TOOL_LOCATION_CACHE: Dict[str, Dict[str, Any]] = {}
LOCATION_CACHE_LOCK = asyncio.Lock()

# Cache for full tool definitions to speed up /definitions (for autocomplete)
DEFINITIONS_CACHE_EXPIRY = timedelta(minutes=5)
BOT_DEFINITIONS_CACHE: Dict[int, Dict[str, Any]] = {}
DEFINITIONS_CACHE_LOCK = asyncio.Lock()


# --- MCP Client Logic ---
JSONRPC_ID_COUNTER = itertools.count(1)

class ToolCallRequest(BaseModel):
    bot_id: int = Field(..., description="The ID of the bot whose tool configuration should be used.")
    tool_name: str = Field(..., description="The name of the tool to call.")
    arguments: Dict[str, Any] = Field(..., description="The arguments for the tool call.")

async def mcp_request(url: str, method: str, params: Dict | None = None, timeout: float = 10.0) -> Dict:
    """
    Sends a JSON-RPC 2.0 request to an MCP server with a configurable timeout.
    """
    payload = {"jsonrpc": "2.0", "method": method, "id": next(JSONRPC_ID_COUNTER)}
    if params:
        payload["params"] = params
    
    async with httpx.AsyncClient() as client:
        headers = {'Content-Type': 'application/json'}
        try:
            response = await client.post(url, content=json.dumps(payload), headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            log.error(f"HTTP request to {url} failed: {e}")
            tools_to_invalidate = [
                tool_name for tool_name, info in TOOL_LOCATION_CACHE.items() if info['url'] == url
            ]
            if tools_to_invalidate:
                log.warning(f"Server at {url} seems down. Invalidating location cache for tools: {', '.join(tools_to_invalidate)}.")
                async with LOCATION_CACHE_LOCK:
                    for tool_name in tools_to_invalidate:
                        TOOL_LOCATION_CACHE.pop(tool_name, None)
            raise ToolServerError(f"Tool server at {url} is unavailable.")
        except json.JSONDecodeError as e:
            log.error(f"Failed to decode JSON response from {url}: {e}")
            raise ToolServerError(f"Invalid response from tool server at {url}.")

class ToolServerError(Exception):
    """Custom exception for tool server communication errors."""
    pass

def create_error_tool_result(message: str) -> Dict[str, Any]:
    """Creates a standardized tool result dictionary for errors."""
    return {"content": [{"type": "text", "text": message}]}


@router.get("/definitions", response_model=List[Dict[str, Any]])
async def get_tool_definitions(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves and aggregates all tool definitions from the MCP servers associated with a bot.
    Results are cached to support features like dynamic command autocompletion.
    """
    now = datetime.now(timezone.utc)
    cached_entry = BOT_DEFINITIONS_CACHE.get(bot_id)
    if cached_entry and (now - cached_entry["timestamp"]) < DEFINITIONS_CACHE_EXPIRY:
        log.info(f"Cache hit for tool definitions for bot {bot_id}.")
        return cached_entry["data"]

    async with DEFINITIONS_CACHE_LOCK:
        # Double-check cache in case it was populated while waiting for the lock
        cached_entry = BOT_DEFINITIONS_CACHE.get(bot_id)
        if cached_entry and (now - cached_entry["timestamp"]) < DEFINITIONS_CACHE_EXPIRY:
            return cached_entry["data"]

        bot = crud_bots.get_bot(db, bot_id=bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail=f"Bot with ID {bot_id} not found.")

        tasks = []
        server_urls = []
        if bot.mcp_server_associations:
            for association in bot.mcp_server_associations:
                server = association.mcp_server
                if not server or not server.enabled:
                    continue
                server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
                server_urls.append(server_url)
                tasks.append(mcp_request(server_url, "tools/list", timeout=5.0))
        
        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_results = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                log.error(f"Failed to fetch tool definitions from {server_urls[i]}: {res}")
                continue
            if res and isinstance(res.get("result"), dict):
                tools = res["result"].get("tools", [])
                successful_results.append(tools)

        all_definitions = list(itertools.chain.from_iterable(successful_results))
        
        BOT_DEFINITIONS_CACHE[bot_id] = {"timestamp": now, "data": all_definitions}
        log.info(f"Cached {len(all_definitions)} tool definitions for bot {bot_id}.")
        
        return all_definitions


@router.post("/call")
async def execute_tool_call(request: ToolCallRequest, db: Session = Depends(get_db)):
    """
    Executes a tool call on the appropriate MCP server, using the bot's specific configuration.
    This endpoint uses an in-memory cache to avoid repeated network discovery for tools.
    """
    bot = crud_bots.get_bot(db, bot_id=request.bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot with ID {request.bot_id} not found.")

    try:
        # --- Discovery Logic ---
        target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)

        if not target_server_info:
            async with LOCATION_CACHE_LOCK:
                target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
                if not target_server_info:
                    log.info(f"Cache miss for tool '{request.tool_name}'. Starting discovery for bot {bot.id}.")
                    if bot.mcp_server_associations:
                        for association in bot.mcp_server_associations:
                            server = association.mcp_server
                            if not server or not server.enabled:
                                continue
                            
                            server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
                            try:
                                rpc_response = await mcp_request(server_url, "tools/list", timeout=20.0)
                                server_tools = rpc_response.get("result", {}).get("tools", [])
                                
                                for tool in server_tools:
                                    tool_name = tool.get('name')
                                    if tool_name and tool_name not in TOOL_LOCATION_CACHE:
                                        TOOL_LOCATION_CACHE[tool_name] = {"url": server_url, "server_id": server.id}
                                        log.info(f"Cached tool '{tool_name}' at {server_url}")
                            
                            except ToolServerError as e:
                                log.error(f"Could not discover tools from {server_url} for bot {bot.id}: {e}")
                                continue
                    
                    target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
        
        if not target_server_info:
            log.error(f"Tool '{request.tool_name}' not found for bot {bot.id} after discovery.")
            return create_error_tool_result(f"Error: Tool '{request.tool_name}' could not be found or its server is unavailable.")

        # --- Execution Logic ---
        server_url = target_server_info["url"]
        target_server_id = target_server_info["server_id"]
        
        params = {"name": request.tool_name, "arguments": request.arguments}
        
        association = next((assoc for assoc in bot.mcp_server_associations if assoc.mcp_server_id == target_server_id), None)
        if association and association.configuration:
            params["configuration"] = association.configuration

        log.info(f"Executing tool '{request.tool_name}' on {server_url} for bot {bot.id} (from cache: {'yes' if TOOL_LOCATION_CACHE.get(request.tool_name) else 'no'})")
        
        rpc_response = await mcp_request(server_url, "tools/call", params, timeout=300.0)
        
        # CORRIGÉ : On ne traite une erreur que si la clé 'error' existe et n'est pas nulle.
        if rpc_response.get("error"):
            error_details = rpc_response["error"]
            log.error(f"Error from tool server {server_url}: {error_details}")
            
            message = "Unknown error"
            if isinstance(error_details, dict):
                message = error_details.get('message', str(error_details))
            else:
                message = str(error_details)
            
            return create_error_tool_result(f"Tool execution failed with error: {message}")

        return rpc_response.get("result", create_error_tool_result("Error: Malformed success response from tool server (missing 'result' key)."))

    except ToolServerError as e:
        log.error(f"A tool server communication error occurred for tool '{request.tool_name}': {e}", exc_info=True)
        return create_error_tool_result(f"Error: There was a problem communicating with the tool server. It might be offline or busy. Details: {e}")
    except Exception as e:
        log.error(f"An unexpected error occurred while executing tool '{request.tool_name}': {e}", exc_info=True)
        return create_error_tool_result(f"An unexpected internal error occurred in the tool proxy: {str(e)}")