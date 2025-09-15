####
# app/api/tools_api.py
####
import json
import httpx
import logging
import itertools
from typing import Dict, Any

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
        response = await client.post(url, content=json.dumps(payload), headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()

@router.post("/call")
async def execute_tool_call(request: ToolCallRequest, db: Session = Depends(get_db)):
    """
    Executes a tool call on the appropriate MCP server, using the bot's specific configuration.
    """
    bot = crud_bots.get_bot(db, bot_id=request.bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail=f"Bot with ID {request.bot_id} not found.")

    # Find the server that provides the requested tool
    target_server = None
    if bot.mcp_servers:
        for server in bot.mcp_servers:
            if not server.enabled: continue
            server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
            try:
                # Use a short timeout for discovery, as it should be fast.
                rpc_response = await mcp_request(server_url, "tools/list", timeout=5.0)
                server_tools = rpc_response.get("result", {}).get("tools", [])
                if any(tool['name'] == request.tool_name for tool in server_tools):
                    target_server = server
                    break
            except Exception as e:
                log.error(f"Could not discover tools from {server_url} for bot {bot.id}: {e}")
                continue
    
    if not target_server:
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found or its server is unavailable for bot {bot.id}.")

    # Execute the tool call
    try:
        server_url = f"http://{target_server.host}:{target_server.port}{target_server.rpc_endpoint_path}"
        params = {"name": request.tool_name, "arguments": request.arguments}
        
        association = next((assoc for assoc in bot.mcp_server_associations if assoc.mcp_server_id == target_server.id), None)
        if association and association.configuration:
            params["configuration"] = association.configuration

        log.info(f"Executing tool '{request.tool_name}' on {server_url} for bot {bot.id}")
        # Use a long timeout for the actual tool call, as it can be slow.
        rpc_response = await mcp_request(server_url, "tools/call", params, timeout=300.0)
        return rpc_response.get("result", {"error": rpc_response.get("error", "Unknown error from tool server.")})

    except Exception as e:
        log.error(f"Failed to execute tool '{request.tool_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))