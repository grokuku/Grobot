# app/database/crud_mcp.py
from sqlalchemy.orm import Session
from app.database import sql_models as models
from app.schemas import mcp_schemas as schemas
from typing import List, Optional

def get_mcp_server(db: Session, server_id: int) -> Optional[models.MCPServer]:
    """
    Retrieves a single MCP server by its ID.
    """
    return db.query(models.MCPServer).filter(models.MCPServer.id == server_id).first()

def get_mcp_server_by_name(db: Session, name: str) -> Optional[models.MCPServer]:
    """
    Retrieves a single MCP server by its name.
    """
    return db.query(models.MCPServer).filter(models.MCPServer.name == name).first()

def get_mcp_servers(db: Session, skip: int = 0, limit: int = 100) -> List[models.MCPServer]:
    """
    Retrieves a list of all MCP servers with pagination.
    """
    return db.query(models.MCPServer).offset(skip).limit(limit).all()

def create_mcp_server(db: Session, server: schemas.MCPServerCreate) -> models.MCPServer:
    """
    Creates a new MCP server in the database.
    """
    db_server = models.MCPServer(**server.model_dump())
    db.add(db_server)
    db.commit()
    db.refresh(db_server)
    return db_server

def update_mcp_server(db: Session, server_id: int, server_update: schemas.MCPServerUpdate) -> Optional[models.MCPServer]:
    """
    Updates an existing MCP server.
    """
    db_server = get_mcp_server(db, server_id)
    if not db_server:
        return None
    
    update_data = server_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_server, key, value)
        
    db.commit()
    db.refresh(db_server)
    return db_server

def delete_mcp_server(db: Session, server_id: int) -> Optional[models.MCPServer]:
    """
    Deletes an MCP server from the database.
    """
    db_server = get_mcp_server(db, server_id)
    if not db_server:
        return None
    
    db.delete(db_server)
    db.commit()
    return db_server