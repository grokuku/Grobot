#### Fichier: app/api/tools_api.py
import json
import httpx
import logging
import itertools
import time  # <--- Ajout pour le timing
from fastapi.responses import JSONResponse
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import crud_bots
from app.database.sql_session import get_db

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

JSONRPC_ID_COUNTER = itertools.count(1)

TOOL_LOCATION_CACHE: Dict[str, Dict[str, Any]] = {}
LOCATION_CACHE_LOCK = asyncio.Lock()
DEFINITIONS_CACHE_EXPIRY = timedelta(minutes=5)
BOT_DEFINITIONS_CACHE: Dict[int, Dict[str, Any]] = {}
DEFINITIONS_CACHE_LOCK = asyncio.Lock()

class ToolDefinition(BaseModel):
    name: str
    description: Optional[str] = ""
    inputSchema: Dict[str, Any]
    is_slow: bool = Field(default=False)
    reaction_emoji: Optional[str] = None

class ToolCallRequest(BaseModel):
    bot_id: int
    tool_name: str
    arguments: Dict[str, Any]

async def mcp_request(url: str, method: str, params: Dict | None = None, timeout: float = 10.0) -> Optional[Dict]:
    payload = {"jsonrpc": "2.0", "method": method, "id": next(JSONRPC_ID_COUNTER)}
    if params: payload["params"] = params
    async with httpx.AsyncClient() as client:
        headers = {'Content-Type': 'application/json'}
        try:
            response = await client.post(url, content=json.dumps(payload), headers=headers, timeout=timeout)
            response.raise_for_status()
            # Handle cases where the response is empty but status is 200 OK
            if not response.content:
                return None
            return response.json()
        except (httpx.RequestError, json.JSONDecodeError) as e:
            log.error(f"MCP_REQUEST FAILED for {url}: {e}")
            raise ToolServerError(f"MCP request failed for {url}")

class ToolServerError(Exception): pass

def create_error_tool_result(message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "error": {"code": -32603, "message": message}, "id": next(JSONRPC_ID_COUNTER)}

@router.get("/definitions", response_model=List[ToolDefinition])
async def get_tool_definitions(bot_id: int, db: Session = Depends(get_db)):
    try:
        now = datetime.now(timezone.utc)
        cached_entry = BOT_DEFINITIONS_CACHE.get(bot_id)
        if cached_entry and (now - cached_entry["timestamp"]) < DEFINITIONS_CACHE_EXPIRY:
            # log.info(f"Tool definitions for bot {bot_id} served from cache.") # Décommenter pour du debug verbeux
            return cached_entry["data"]

        async with DEFINITIONS_CACHE_LOCK:
            # --- START OF LOGGING MODIFICATION ---
            log.info(f"Cache miss for bot {bot_id}. Starting tool discovery.")
            discovery_start_time = time.monotonic()

            bot = crud_bots.get_bot(db, bot_id=bot_id)
            if not bot: raise HTTPException(status_code=404, detail=f"Bot with ID {bot_id} not found.")

            tasks, associations_in_order = [], []
            if bot.mcp_server_associations:
                for association in bot.mcp_server_associations:
                    server = association.mcp_server
                    if server and server.enabled:
                        server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
                        tasks.append(mcp_request(server_url, "tools/list", timeout=5.0))
                        associations_in_order.append(association)
            
            if not tasks: 
                log.warning(f"No active MCP servers found for bot {bot_id}.")
                return []

            log.info(f"Querying {len(tasks)} MCP server(s) for bot {bot_id}...")
            network_call_start_time = time.monotonic()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            network_duration = time.monotonic() - network_call_start_time
            log.info(f"MCP server network calls completed in {network_duration:.4f} seconds.")
            # --- END OF LOGGING MODIFICATION ---
            
            validated_definitions: List[ToolDefinition] = []
            for i, res in enumerate(results):
                association = associations_in_order[i]
                server_url = f"http://{association.mcp_server.host}:{association.mcp_server.port}{association.mcp_server.rpc_endpoint_path}"

                if isinstance(res, Exception) or res is None:
                    log.error(f"Failed to process server '{server_url}'. Error: {res}", exc_info=False)
                    continue
                
                base_tools = res.get("result", {}).get("tools", [])
                db_config = association.configuration or {}

                for tool_def_dict in base_tools:
                    await asyncio.sleep(0) 
                    try:
                        tool_name = tool_def_dict.get("name")
                        if not tool_name: continue

                        tool_specific_db_config = (db_config.get("tool_config") or {}).get(tool_name, {})
                        enriched_def_dict = tool_def_dict.copy()
                        enriched_def_dict.update(tool_specific_db_config)

                        validated_tool = ToolDefinition.model_validate(enriched_def_dict)
                        validated_definitions.append(validated_tool)
                    except Exception as tool_error:
                        log.warning(f"Skipping tool '{tool_def_dict.get('name')}' from {server_url} due to processing error: {tool_error}")

            BOT_DEFINITIONS_CACHE[bot_id] = {"timestamp": now, "data": validated_definitions}
            total_duration = time.monotonic() - discovery_start_time
            log.info(f"Refreshed cache with {len(validated_definitions)} tools for bot {bot_id}. Total discovery time: {total_duration:.4f} seconds.")
            return validated_definitions

    except Exception as e:
        log.error(f"A fatal error occurred in get_tool_definitions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while fetching tool definitions.")

@router.post("/call")
async def execute_tool_call(request: ToolCallRequest, db: Session = Depends(get_db)):
    bot = crud_bots.get_bot(db, bot_id=request.bot_id)
    if not bot: raise HTTPException(status_code=404, detail=f"Bot with ID {request.bot_id} not found.")
    try:
        target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
        if not target_server_info:
            async with LOCATION_CACHE_LOCK:
                target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
                if not target_server_info:
                    log.info(f"Cache miss for tool '{request.tool_name}'. Starting discovery.")
                    if bot.mcp_server_associations:
                        for association in bot.mcp_server_associations:
                            server = association.mcp_server
                            if not server or not server.enabled: continue
                            server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
                            try:
                                rpc_response = await mcp_request(server_url, "tools/list", timeout=20.0)
                                if rpc_response:
                                    for tool in rpc_response.get("result", {}).get("tools", []):
                                        tool_name = tool.get('name')
                                        if tool_name and tool_name not in TOOL_LOCATION_CACHE:
                                            TOOL_LOCATION_CACHE[tool_name] = {"url": server_url, "server_id": server.id}
                                            log.info(f"Cached tool '{tool_name}' at {server_url}")
                            except ToolServerError: continue
                    target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
        if not target_server_info:
            log.error(f"Tool '{request.tool_name}' not found for bot {bot.id} after discovery.")
            return JSONResponse(content=create_error_tool_result(f"Tool '{request.tool_name}' not found."))
        
        server_url, target_server_id = target_server_info["url"], target_server_info["server_id"]
        params = {"name": request.tool_name, "arguments": request.arguments}
        association = next((a for a in bot.mcp_server_associations if a.mcp_server_id == target_server_id), None)
        if association and association.configuration:
            params["configuration"] = association.configuration
        
        log.info(f"Executing tool '{request.tool_name}' on {server_url}")
        result = await mcp_request(server_url, "tools/call", params, timeout=300.0)
        
        if result and "error" in result and not isinstance(result.get("error"), dict):
            log.warning(f"Normalizing malformed error response from MCP server: {result}")
            result = create_error_tool_result("Tool server returned a malformed error response.")

        if result is None:
            return JSONResponse(content=create_error_tool_result("Tool server returned an empty response."))
        
        return JSONResponse(content=result)
    
    except Exception as e:
        log.error(f"Unexpected error in execute_tool_call: {e}", exc_info=True)
        return JSONResponse(content=create_error_tool_result(f"Internal error in tool proxy: {e}"))