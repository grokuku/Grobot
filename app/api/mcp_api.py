#### Fichier : app/api/mcp_api.py
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Any, Dict

from app.database.sql_session import get_db
from app.database import crud_mcp
from app.schemas import mcp_schemas

router = APIRouter()

@router.post("/mcp-servers/", response_model=mcp_schemas.MCPServerInDB, status_code=status.HTTP_201_CREATED)
def create_mcp_server(
    server: mcp_schemas.MCPServerCreate, db: Session = Depends(get_db)
):
    """
    Create a new MCP server configuration.
    """
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
    Retrieve all MCP server configurations.
    """
    servers = crud_mcp.get_mcp_servers(db, skip=skip, limit=limit)
    return servers

@router.get("/mcp-servers/{server_id}", response_model=mcp_schemas.MCPServerInDB)
def read_mcp_server(server_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a specific MCP server configuration by its ID.
    """
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
    """
    Update an MCP server's configuration.
    """
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    
    # Check if the new name is already taken by another server
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
    """
    Delete an MCP server configuration.
    """
    db_server = crud_mcp.delete_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )
    return db_server


# MODIFIED: Changed response_model to List[Dict] to accurately reflect the output.
@router.get("/mcp-servers/{server_id}/tools", response_model=List[Dict[str, Any]])
async def list_mcp_server_tools(server_id: int, db: Session = Depends(get_db)):
    """
    Acts as a proxy to discover the available tools from a specific MCP server.
    This uses the standard 'tools/list' MCP method.
    """
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="MCP server not found"
        )

    target_url = f"http://{db_server.host}:{db_server.port}{db_server.rpc_endpoint_path}"
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 1, 
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=payload, timeout=5.0)
            response.raise_for_status()
            
            json_response = response.json()

            # CORRECTIF: Gère le cas où la clé "error" existe mais sa valeur est null.
            error_obj = json_response.get("error")
            if error_obj:
                error_details = error_obj.get("message", "Unknown error from tool server")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Tool server returned an error: {error_details}",
                )
            
            # MODIFIED: Extract the 'tools' list from the 'result' object.
            result = json_response.get("result", {})
            return result.get("tools", [])

        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not connect to the MCP server at {target_url}. Error: {exc}",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {exc}",
            )

@router.get("/mcp-servers/{server_id}/config-schema", response_model=Dict[str, Any])
async def get_mcp_server_schema(server_id: int, db: Session = Depends(get_db)):
    """
    Acts as a proxy to get a server-level configuration schema.
    This uses a non-standard 'server/describe' MCP method.
    If the server doesn't support it, it returns a default empty schema.
    """
    db_server = crud_mcp.get_mcp_server(db, server_id=server_id)
    if db_server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")

    target_url = f"http://{db_server.host}:{db_server.port}{db_server.rpc_endpoint_path}"
    payload = {
        "jsonrpc": "2.0",
        "method": "server/describe",
        "params": {},
        "id": 2,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(target_url, json=payload, timeout=3.0)
            
            if response.status_code >= 400:
                return {"type": "object", "properties": {}}

            json_response = response.json()

            # CORRECTIF: Gère le cas où la clé "error" existe mais sa valeur est null.
            if json_response.get("error"):
                    return {"type": "object", "properties": {}}
            
            return json_response.get("result", {"type": "object", "properties": {}})

        except httpx.RequestError:
            return {"type": "object", "properties": {}}