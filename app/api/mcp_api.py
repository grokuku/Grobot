####
# FICHIER: app/api/mcp_api.py
####
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Any, Dict
import logging
import json
import asyncio

from app.database.sql_session import get_db, SessionLocal
from app.database import crud_mcp, crud_bots
from app.schemas import mcp_schemas

logger = logging.getLogger(__name__)

router = APIRouter()

# --- NEW FUNCTION ---
async def get_all_tools_for_bot_internal(bot_id: int, db: Session) -> List[Dict[str, Any]]:
    """
    Retrieves all tool schemas for a given bot from the database cache.

    This is a fast, internal-facing function that reads from the discovered tools
    stored in the database for each MCP server associated with the bot.
    It does NOT perform any network calls.
    """
    bot = crud_bots.get_bot_with_mcp_servers(db, bot_id=bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    all_tools = []
    # --- FIX START ---
    # The relationship on the Bot model is named 'mcp_server_associations'.
    for server_association in bot.mcp_server_associations:
    # --- FIX END ---
        mcp_server = server_association.mcp_server
        if mcp_server and mcp_server.enabled and mcp_server.discovered_tools_schema:
            for tool_schema in mcp_server.discovered_tools_schema:
                all_tools.append({
                    "mcp_server_id": mcp_server.id,
                    "tool_definition": tool_schema
                })
    return all_tools

# --- BACKGROUND TASK FOR MCP DISCOVERY ---

async def force_discover_all_servers():
    """
    Connects to the DB, gets all MCP servers, and triggers discovery for each of them.
    This runs in a background task and needs its own DB session.
    """
    logger.info("Background task: Starting force-discovery for all MCP servers.")
    db = SessionLocal()
    try:
        servers = crud_mcp.get_mcp_servers(db, skip=0, limit=1000)
        
        if not servers:
            logger.info("Background task: No MCP servers found to discover.")
            return

        discovery_tasks = [_discover_and_update_if_needed(server, db) for server in servers]
        await asyncio.gather(*discovery_tasks)
        logger.info(f"Background task: Discovery complete for {len(servers)} MCP servers.")

    except Exception as e:
        logger.error(f"Background task: An error occurred during periodic discovery: {e}", exc_info=True)
    finally:
        db.close()

async def background_discovery_task():
    """
    The main loop for the background discovery task.
    Runs once on startup, then every 30 minutes.
    """
    while True:
        await force_discover_all_servers()
        sleep_duration_seconds = 30 * 60
        logger.info(f"Background task: Sleeping for {sleep_duration_seconds / 60} minutes.")
        await asyncio.sleep(sleep_duration_seconds)

# --- HELPER FUNCTION (UNCHANGED) ---
async def _discover_and_update_if_needed(server_model: any, db: Session):
    """
    Internal helper to perform tool discovery for a single server.
    Now used by the background task to unconditionally update the cache.
    """
    target_url = f"http://{server_model.host}:{server_model.port}{server_model.rpc_endpoint_path}"
    payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(target_url, json=payload, timeout=10.0)
            response.raise_for_status()
            json_response = response.json()

        error_obj = json_response.get("error")
        if error_obj is not None:
            raise Exception(f"MCP server returned error payload: {json_response}")

        discovered_tools = json_response.get("result", {}).get("tools", [])
        update_payload = mcp_schemas.MCPServerUpdate(discovered_tools_schema=discovered_tools)
        crud_mcp.update_mcp_server(db=db, server_id=server_model.id, server_update=update_payload)
        logger.info(f"Successfully discovered and cached {len(discovered_tools)} tools for MCP server '{server_model.name}'.")

    except Exception as e:
        logger.error(f"Discovery for MCP server '{server_model.name}' ({target_url}) failed: {e}")

# --- CRUD ENDPOINTS ---

@router.post("/mcp-servers/", response_model=mcp_schemas.MCPServerInDB, status_code=status.HTTP_201_CREATED)
def create_mcp_server(
    server: mcp_schemas.MCPServerCreate, db: Session = Depends(get_db)
):
    db_server = crud_mcp.get_mcp_server_by_name(db, name=server.name)
    if db_server:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An MCP server with the name '{server.name}' already exists.",
        )
    return crud_mcp.create_mcp_server(db=db, server=server)

@router.get("/mcp-servers/", response_model=List[mcp_schemas.MCPServerInDB])
def read_mcp_servers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieve all MCP server configurations from the database.
    Discovery is now handled by a background task.
    """
    servers = crud_mcp.get_mcp_servers(db, skip=skip, limit=limit)
    return servers

@router.get("/mcp-servers/{server_id}", response_model=mcp_schemas.MCPServerInDB)
def read_mcp_server(server_id: int, db: Session = Depends(get_db)):
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    return db_server

@router.patch("/mcp-servers/{server_id}", response_model=mcp_schemas.MCPServerInDB)
def update_mcp_server(
    server_id: int,
    server_update: mcp_schemas.MCPServerUpdate,
    db: Session = Depends(get_db),
):
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    
    if server_update.name and server_update.name != db_server.name:
        existing_server = crud_mcp.get_mcp_server_by_name(db, name=server_update.name)
        if existing_server:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An MCP server with the name '{server_update.name}' already exists.",
            )

    return crud_mcp.update_mcp_server(db=db, server_id=server_id, server_update=server_update)

@router.delete("/mcp-servers/{server_id}", response_model=mcp_schemas.MCPServerInDB)
def delete_mcp_server(server_id: int, db: Session = Depends(get_db)):
    db_server = crud_mcp.delete_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    return db_server

@router.post("/mcp-servers/{server_id}/discover-tools", response_model=mcp_schemas.MCPServerInDB)
async def discover_and_cache_mcp_tools(server_id: int, db: Session = Depends(get_db)):
    """
    Manually triggers tool discovery for an MCP server and caches the results.
    """
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if not db_server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found")

    await _discover_and_update_if_needed(db_server, db)
    
    return crud_mcp.get_mcp_server(db, server_id=server_id)

@router.get("/mcp-servers/{server_id}/tools", response_model=List[Dict[str, Any]])
def list_mcp_server_tools(server_id: int, db: Session = Depends(get_db)):
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    return db_server.discovered_tools_schema or []

@router.get("/mcp-servers/{server_id}/config-schema", response_model=Dict[str, Any])
async def get_mcp_server_schema(server_id: int, db: Session = Depends(get_db)):
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")

    target_url = f"http://{db_server.host}:{db_server.port}{db_server.rpc_endpoint_path}"
    payload = {"jsonrpc": "2.0", "method": "server/describe", "params": {}, "id": 2}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=payload, timeout=3.0)
            if response.status_code >= 400:
                return {"type": "object", "properties": {}}
            json_response = response.json()
            if json_response.get("error"):
                    return {"type": "object", "properties": {}}
            return json_response.get("result", {"type": "object", "properties": {}})

        except httpx.RequestError:
            return {"type": "object", "properties": {}}