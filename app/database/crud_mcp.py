#### Fichier : app/database/crud_mcp.py
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from app.database import sql_models as models
from app.schemas import mcp_schemas as schemas
from typing import List, Optional

def get_association(db: Session, bot_id: int, mcp_server_id: int) -> Optional[models.BotMCPServerAssociation]:
    """
    Retrieves the association object between a bot and an MCP server,
    which contains the bot-specific configuration for that server's tools.
    """
    return db.execute(
        select(models.BotMCPServerAssociation).where(
            models.BotMCPServerAssociation.bot_id == bot_id,
            models.BotMCPServerAssociation.mcp_server_id == mcp_server_id
        )
    ).scalar_one_or_none()

# --- CORRECTION DE LA REQUÊTE 'JOINEDLOAD' ---
def get_mcp_servers_for_bot(db: Session, bot_id: int) -> List[models.MCPServer]:
    """
    Retrieves all *enabled* MCP servers associated with a specific bot
    using an efficient query.
    """
    # On charge la relation directe 'mcp_server_associations', PUIS la relation
    # 'mcp_server' depuis l'objet d'association.
    bot = db.query(models.Bot).filter(models.Bot.id == bot_id).options(
        joinedload(models.Bot.mcp_server_associations).joinedload(models.BotMCPServerAssociation.mcp_server)
    ).first()

    if not bot:
        return []
    
    # On reconstruit la liste des serveurs à partir du chemin chargé, en filtrant les serveurs désactivés.
    return [
        association.mcp_server 
        for association in bot.mcp_server_associations 
        if association.mcp_server and association.mcp_server.enabled
    ]

# --- Fonctions existantes (inchangées) ---

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