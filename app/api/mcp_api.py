####
# FICHIER: app/api/mcp_api.py
####
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Any, Dict
import logging
import json
import asyncio

# --- NEW: MCP-Use Import ---
from mcp_use import MCPClient
# ---------------------------

from app.database.sql_session import get_db, SessionLocal
from app.database import crud_mcp, crud_bots
from app.schemas import mcp_schemas

logger = logging.getLogger(__name__)

router = APIRouter()

# --- INTERNAL FUNCTION (Optimized) ---
async def get_all_tools_for_bot_internal(bot_id: int, db: Session) -> List[Dict[str, Any]]:
    """
    Retrieves all tool schemas for a given bot from the database cache.
    """
    bot = crud_bots.get_bot_with_mcp_servers(db, bot_id=bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    all_tools = []
    # Use the correct relationship name
    for server_association in bot.mcp_server_associations:
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
    """
    while True:
        await force_discover_all_servers()
        sleep_duration_seconds = 30 * 60
        logger.info(f"Background task: Sleeping for {sleep_duration_seconds / 60} minutes.")
        await asyncio.sleep(sleep_duration_seconds)

# --- HELPER FUNCTION (REFACTORED for MCP-Use) ---
async def _discover_and_update_if_needed(server_model: any, db: Session):
    """
    Internal helper to perform tool discovery for a single server using MCP-Use.
    MODIFIED: Explicitly disables OAuth and adds timeouts for MCPHub compatibility.
    """
    # FIX 1: Ensure no trailing slash
    base_url = f"http://{server_model.host}:{server_model.port}{server_model.rpc_endpoint_path}".rstrip('/')
    
    # Configuration for MCP-Use
    config = {
        "mcpServers": {
            "discovery_session": {
                "transport": "sse",
                "url": base_url,
                # FIX 2: Explicitly disable OAuth discovery to prevent mcp-use from hanging
                "oauth": False
            }
        }
    }
    
    try:
        # Initialize Client
        client = MCPClient(config)
        
        # FIX 3: Timeout to prevent the background task from blocking if server is slow
        await asyncio.wait_for(client.create_all_sessions(), timeout=10.0)
        
        session = client.get_session("discovery_session")
        if not session:
             raise Exception("Failed to establish session for discovery.")

        # List tools
        tools = await session.list_tools()
        
        # Format for Database
        discovered_tools = []
        for tool in tools:
            discovered_tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema or {}
            })

        # Update DB
        update_payload = mcp_schemas.MCPServerUpdate(discovered_tools_schema=discovered_tools)
        crud_mcp.update_mcp_server(db=db, server_id=server_model.id, server_update=update_payload)
        logger.info(f"Successfully discovered and cached {len(discovered_tools)} tools for MCP server '{server_model.name}'.")

    except asyncio.TimeoutError:
        logger.warning(f"Discovery timeout for MCP server '{server_model.name}' at {base_url}. Skipping.")
    except Exception as e:
        logger.error(f"Discovery for MCP server '{server_model.name}' ({base_url}) failed: {e}")

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
    """
    Legacy support: Returns empty schema as 'server/describe' is not standard MCP.
    """
    return {"type": "object", "properties": {}}