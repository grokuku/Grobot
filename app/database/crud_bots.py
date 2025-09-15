# app/database/crud_bots.py

import time
from typing import List
from sqlalchemy.orm import Session, joinedload

# MODIFIÉ : Import de la nouvelle classe 'BotMCPServerAssociation'
from app.database.sql_models import Bot, MCPServer, BotMCPServerAssociation
from app.schemas import bot_schemas, mcp_schemas

def get_bot(db: Session, bot_id: int) -> Bot | None:
    """
    Retrieves a bot by its ID, eagerly loading its associated MCP servers
    and their specific configurations for this bot using the Association Object pattern.
    """
    # MODIFIÉ : Utilise joinedload sur les nouvelles relations pour charger toutes les données en une seule requête.
    db_bot = db.query(Bot).options(
        joinedload(Bot.mcp_server_associations).joinedload(BotMCPServerAssociation.mcp_server)
    ).filter(Bot.id == bot_id).first()

    if not db_bot:
        return None

    # MODIFIÉ : Logique de "stitching" simplifiée.
    # On attache dynamiquement la configuration de l'association directement sur l'objet serveur
    # pour que Pydantic puisse le valider correctement.
    for association in db_bot.mcp_server_associations:
        association.mcp_server.configuration = association.configuration

    return db_bot

def get_bot_by_name(db: Session, name: str) -> Bot | None:
    """
    Retrieves a bot by its unique name.
    """
    return db.query(Bot).filter(Bot.name == name).first()

def get_bots(db: Session, skip: int = 0, limit: int = 100) -> list[Bot]:
    """
    Retrieves a list of bots with pagination, including their MCP server configurations.
    """
    # MODIFIÉ : Utilise la même stratégie de chargement optimisée que get_bot.
    bots = db.query(Bot).options(
        joinedload(Bot.mcp_server_associations).joinedload(BotMCPServerAssociation.mcp_server)
    ).offset(skip).limit(limit).all()

    if not bots:
        return []

    # MODIFIÉ : Logique de "stitching" simplifiée pour chaque bot de la liste.
    for bot in bots:
        for association in bot.mcp_server_associations:
            association.mcp_server.configuration = association.configuration
            
    return bots

def create_bot(db: Session, bot: bot_schemas.BotCreate) -> Bot:
    """
    Creates a new bot.
    """
    # This logic allows creating a bot for pre-configuration even without
    # a valid Discord token. A unique placeholder is used if no token is provided.
    token_to_use = bot.discord_token
    if not token_to_use:
        # The placeholder is not used for authentication but to satisfy the unique constraint.
        token_to_use = f"PLACEHOLDER_TOKEN_{bot.name.replace(' ', '_')}_{int(time.time())}"

    db_bot = Bot(
        name=bot.name,
        discord_token=token_to_use,
        system_prompt=bot.system_prompt,
        llm_model=bot.llm_model,
        passive_listening_enabled=bot.passive_listening_enabled,
        gatekeeper_history_limit=bot.gatekeeper_history_limit,
        conversation_history_limit=bot.conversation_history_limit
    )
    db.add(db_bot)
    db.commit()
    db.refresh(db_bot)
    return db_bot

def update_bot(db: Session, bot_id: int, bot_update: bot_schemas.BotUpdate) -> Bot | None:
    """
    Updates an existing bot's core attributes.
    NOTE: MCP server associations are managed via a dedicated endpoint.
    """
    db_bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not db_bot:
        return None

    update_data = bot_update.model_dump(exclude_unset=True)
    update_data.pop('mcp_server_ids', None) # Associations are not handled here.

    for key, value in update_data.items():
        if hasattr(db_bot, key):
            setattr(db_bot, key, value)

    db.add(db_bot)
    db.commit()
    
    # Retourne le bot complet avec les données d'association à jour.
    return get_bot(db, bot_id)


def update_bot_mcp_servers(
    db: Session, 
    bot_id: int, 
    mcp_associations: List[mcp_schemas.MCPServerAssociationConfig]
) -> Bot | None:
    """
    Updates the MCP server associations for a bot using the ORM.
    This is an atomic operation that replaces the existing associations.
    """
    # MODIFIÉ : Utilise la manipulation de relation ORM, beaucoup plus propre et sûre.
    db_bot = db.query(Bot).options(joinedload(Bot.mcp_server_associations)).filter(Bot.id == bot_id).first()
    if not db_bot:
        return None
    
    # 1. Vider la collection existante. La configuration "cascade='all, delete-orphan'"
    # s'occupera de supprimer les anciennes entrées de la base de données.
    db_bot.mcp_server_associations.clear()
    
    # 2. Créer les nouveaux objets d'association et les ajouter à la session.
    for assoc_data in mcp_associations:
        new_association = BotMCPServerAssociation(
            mcp_server_id=assoc_data.mcp_server_id,
            configuration=assoc_data.configuration
        )
        db_bot.mcp_server_associations.append(new_association)
        
    db.commit()
    
    return get_bot(db, bot_id)


def delete_bot(db: Session, bot_id: int) -> Bot | None:
    """
    Deletes a bot by its ID.
    """
    db_bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not db_bot:
        return None
        
    db.delete(db_bot)
    db.commit()
    return db_bot