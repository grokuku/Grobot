#### Fichier: app/api/tools_api.py
import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# --- NEW IMPORTS FOR MCP-USE & HTTPX ---
from mcp_use import MCPClient
import httpx
# -------------------------------

from app.database import crud_bots
from app.database.sql_session import get_db

router = APIRouter(
    prefix="/tools",
    tags=["Tools"],
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Caches
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

# --- HELPER: Build MCP Client Config ---
def build_mcp_config(servers: List[Any]) -> Dict[str, Any]:
    """
    Constructs the configuration dictionary required by MCPClient
    from a list of MCPServer database models.
    """
    mcp_servers_config = {}
    for server in servers:
        # We construct a unique key for the session based on ID
        server_key = f"server_{server.id}"
        
        # Standard MCP over HTTP usually implies SSE/Streamable transport.
        # We use the URL from the DB. 
        # FIX: Ensure no trailing slash which confuses mcp-use discovery
        base_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}".rstrip('/')
        
        mcp_servers_config[server_key] = {
            "transport": "sse", # Defaulting to SSE as per standard MCP HTTP usage
            "url": base_url,
            # FIX: Explicitly disable OAuth to prevent OIDC discovery issues with MCPHub
            "oauth": False
        }
    
    return {"mcpServers": mcp_servers_config}

@router.get("/definitions", response_model=List[ToolDefinition])
async def get_tool_definitions(bot_id: int, db: Session = Depends(get_db)):
    try:
        now = datetime.now(timezone.utc)
        cached_entry = BOT_DEFINITIONS_CACHE.get(bot_id)
        if cached_entry and (now - cached_entry["timestamp"]) < DEFINITIONS_CACHE_EXPIRY:
            return cached_entry["data"]

        async with DEFINITIONS_CACHE_LOCK:
            log.info(f"Cache miss for bot {bot_id}. Starting tool discovery with MCP-Use.")
            discovery_start_time = time.monotonic()

            bot = crud_bots.get_bot(db, bot_id=bot_id)
            if not bot: raise HTTPException(status_code=404, detail=f"Bot with ID {bot_id} not found.")

            # Identify active servers
            active_servers = []
            associations_map = {} # Map server_id -> association
            if bot.mcp_server_associations:
                for association in bot.mcp_server_associations:
                    if association.mcp_server and association.mcp_server.enabled:
                        active_servers.append(association.mcp_server)
                        associations_map[association.mcp_server.id] = association

            if not active_servers:
                log.warning(f"No active MCP servers found for bot {bot_id}.")
                return []

            validated_definitions: List[ToolDefinition] = []

            # --- ISOLATED DISCOVERY LOOP WITH RETRY ---
            # We treat each server independently to prevent one failure from blocking all tools.
            for server in active_servers:
                server_key = f"server_{server.id}"
                
                # Config just for this server
                single_server_config = build_mcp_config([server])
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        client = MCPClient(single_server_config)
                        
                        # SAFETY FIX: Add timeout to prevent blocking on OIDC/OAuth discovery
                        # We use a timeout even with oauth=False as a safety measure
                        await asyncio.wait_for(client.create_all_sessions(), timeout=10.0)
                        
                        session = client.get_session(server_key)
                        if not session:
                            log.warning(f"Could not get session for {server.name} ({server_key})")
                            break # Config error likely, don't retry

                        # List tools
                        mcp_tools = await session.list_tools()
                        
                        # Retrieve specific config for this bot/server association
                        association = associations_map.get(server.id)
                        db_config = association.configuration or {} if association else {}

                        for tool in mcp_tools:
                            # Merge with DB config (overrides)
                            tool_specific_db_config = (db_config.get("tool_config") or {}).get(tool.name, {})
                            
                            # Build the definition dictionary
                            def_dict = {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.inputSchema or {},
                            }
                            def_dict.update(tool_specific_db_config)
                            
                            validated_definitions.append(ToolDefinition.model_validate(def_dict))
                        
                        # Success, break retry loop
                        break 
                    
                    except asyncio.TimeoutError:
                         log.warning(f"Timeout discovering tools on {server.name}. Skipping.")
                         break

                    except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as net_err:
                        log.warning(f"Network error discovering tools on {server.name} (Attempt {attempt+1}/{max_retries}): {net_err}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5)
                        else:
                            log.error(f"Failed to discover tools on {server.name} after retries.")
                    except Exception as e:
                        log.error(f"Error listing tools for server {server.name}: {e}")
                        break # Non-network error, don't retry

            BOT_DEFINITIONS_CACHE[bot_id] = {"timestamp": now, "data": validated_definitions}
            total_duration = time.monotonic() - discovery_start_time
            log.info(f"Refreshed cache with {len(validated_definitions)} tools for bot {bot_id}. Total time: {total_duration:.4f}s")
            return validated_definitions

    except Exception as e:
        log.error(f"A fatal error occurred in get_tool_definitions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred while fetching tool definitions.")

@router.post("/call")
async def execute_tool_call(request: ToolCallRequest, db: Session = Depends(get_db)):
    bot = crud_bots.get_bot(db, bot_id=request.bot_id)
    if not bot: raise HTTPException(status_code=404, detail=f"Bot with ID {request.bot_id} not found.")
    
    try:
        # 1. Resolve Tool Location (Cache or Discovery)
        target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
        target_server_model = None

        if not target_server_info:
            async with LOCATION_CACHE_LOCK:
                # Double-check locking
                target_server_info = TOOL_LOCATION_CACHE.get(request.tool_name)
                if not target_server_info:
                    log.info(f"Cache miss for tool '{request.tool_name}'. Quick discovery...")
                    # Quick discovery logic (simplified to reduce code duplication)
                    # We just try to find which server has it
                    active_servers = [
                        assoc.mcp_server for assoc in bot.mcp_server_associations 
                        if assoc.mcp_server and assoc.mcp_server.enabled
                    ]
                    
                    for server in active_servers:
                        # Try to connect one by one
                        try:
                            cfg = build_mcp_config([server])
                            cl = MCPClient(cfg)
                            # SAFETY FIX: Timeout
                            await asyncio.wait_for(cl.create_all_sessions(), timeout=5.0)
                            
                            sess = cl.get_session(f"server_{server.id}")
                            if sess:
                                tools = await sess.list_tools()
                                for t in tools:
                                    TOOL_LOCATION_CACHE[t.name] = {"server_id": server.id}
                                    if t.name == request.tool_name:
                                        target_server_info = {"server_id": server.id}
                        except Exception:
                            continue # Try next server
                        
                        if target_server_info: break

        if not target_server_info:
            return JSONResponse(content={
                "jsonrpc": "2.0", 
                "error": {"code": -32601, "message": f"Tool '{request.tool_name}' not found."}
            })

        # 2. Get the specific server model
        target_server_id = target_server_info["server_id"]
        from app.database import crud_mcp
        target_server_model = crud_mcp.get_mcp_server(db, target_server_id)
        
        if not target_server_model:
             return JSONResponse(content={
                "jsonrpc": "2.0", 
                "error": {"code": -32603, "message": "Associated MCP server not found in DB."}
            })

        # 3. Execute with MCP Client (WITH RETRY)
        config = build_mcp_config([target_server_model])
        server_key = f"server_{target_server_model.id}"

        log.info(f"Executing tool '{request.tool_name}' on server {target_server_model.name} via MCP-Use")
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Create fresh client per attempt to ensure clean state
                client = MCPClient(config)
                
                # SAFETY FIX: Timeout for execution session creation
                await asyncio.wait_for(client.create_all_sessions(), timeout=15.0)
                
                session = client.get_session(server_key)
                
                if not session:
                     raise Exception("Failed to establish session with MCP server.")

                # EXECUTE
                result = await session.call_tool(
                    name=request.tool_name,
                    arguments=request.arguments
                )
                
                # 4. Format Result
                response_content = []
                if hasattr(result, "content") and isinstance(result.content, list):
                    for item in result.content:
                        if hasattr(item, "type") and hasattr(item, "text"):
                             response_content.append({"type": "text", "text": item.text})
                        elif hasattr(item, "type") and item.type == "image":
                             response_content.append({
                                 "type": "image", 
                                 "data": item.data, 
                                 "mimeType": item.mimeType
                             })
                        else:
                            response_content.append(item.model_dump() if hasattr(item, "model_dump") else str(item))
                
                is_error = getattr(result, "isError", False)
                
                json_response = {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": response_content,
                        "isError": is_error
                    },
                    "id": 1
                }
                
                return JSONResponse(content=json_response)

            except asyncio.TimeoutError:
                last_error = "Timeout during tool execution setup"
                log.warning(f"Timeout executing tool (Attempt {attempt+1}/{max_retries})")

            except (httpx.RemoteProtocolError, httpx.ReadTimeout, httpx.ConnectError) as net_err:
                last_error = net_err
                log.warning(f"Network error executing tool (Attempt {attempt+1}/{max_retries}): {net_err}")
                await asyncio.sleep(0.5)
            
            except Exception as tool_err:
                log.error(f"MCP Execution Error: {tool_err}", exc_info=True)
                return JSONResponse(content={
                    "jsonrpc": "2.0", 
                    "error": {"code": -32603, "message": f"Tool execution failed: {str(tool_err)}"}
                })
        
        # If we exit the loop, it means retries failed
        return JSONResponse(content={
            "jsonrpc": "2.0", 
            "error": {"code": -32603, "message": f"Network/Timeout error after retries: {str(last_error)}"}
        })

    except Exception as e:
        log.error(f"Unexpected error in execute_tool_call: {e}", exc_info=True)
        return JSONResponse(content={
            "jsonrpc": "2.0", 
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        })