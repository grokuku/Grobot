# app/api/bots_api.py
import traceback
import asyncio
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import crud_bots, crud_settings
from app.database.sql_session import get_db
from app.database.chroma_manager import chroma_manager
from app.schemas import bot_schemas, mcp_schemas
from app.schemas.bot_schemas import LogMessage

# --- Log Broadcasting Manager ---

class LogManager:
    """Manages active WebSocket connections for log streaming."""
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, bot_id: int, websocket: WebSocket):
        """Registers a new WebSocket connection."""
        await websocket.accept()
        if bot_id not in self.active_connections:
            self.active_connections[bot_id] = []
        self.active_connections[bot_id].append(websocket)
        print(f"+++ WebSocket CONNECTED for bot {bot_id}. Total clients now: {len(self.active_connections[bot_id])}")
        print(f"Current state of all connections: {self.active_connections}")


    def disconnect(self, bot_id: int, websocket: WebSocket):
        """Removes a WebSocket connection."""
        if bot_id in self.active_connections:
            self.active_connections[bot_id].remove(websocket)
            print(f"--- WebSocket DISCONNECTED for bot {bot_id}. Remaining clients: {len(self.active_connections.get(bot_id, []))}")
            if not self.active_connections[bot_id]:
                del self.active_connections[bot_id]
        print(f"Current state of all connections: {self.active_connections}")


    async def broadcast(self, bot_id: int, message: str):
        """Sends a message to all connected clients for a specific bot."""
        print(f">>> BROADCAST ATTEMPT for bot_id {bot_id}")
        print(f"    Message: {message}")
        print(f"    Current state of all connections: {self.active_connections}")

        if bot_id in self.active_connections and self.active_connections[bot_id]:
            connections = self.active_connections[bot_id]
            print(f"    Found {len(connections)} active client(s) for this bot.")
            
            tasks = [connection.send_text(message) for connection in connections]
            
            if tasks:
                print(f"    Broadcasting to {len(tasks)} client(s)...")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                print(f"    Broadcast results for bot {bot_id}: {results}")
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(f"    ERROR sending to client {i}: {result}")
        else:
            print(f"    !!! WARNING: No active WebSocket connections found for bot_id {bot_id} during broadcast.")


# Create a single instance of the manager
log_manager = LogManager()


router = APIRouter(
    prefix="/bots",
    tags=["Bots API"],
    responses={404: {"description": "Not found"}},
)

# --- WebSocket Endpoint for Log Streaming ---
@router.websocket("/{bot_id}/logs/ws")
async def websocket_log_stream(websocket: WebSocket, bot_id: int):
    """
    Establishes a WebSocket connection to stream logs for a specific bot.
    """
    await log_manager.connect(bot_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_manager.disconnect(bot_id, websocket)
    except Exception as e:
        print(f"Error in WebSocket for bot {bot_id}: {e}")
        log_manager.disconnect(bot_id, websocket)


# --- Endpoint for Bot Processes to Submit Logs ---
@router.post("/{bot_id}/logs", status_code=status.HTTP_202_ACCEPTED)
async def submit_log(bot_id: int, log_message: LogMessage):
    """
    Receives a log message from a bot process and broadcasts it to WebSocket clients.
    """
    try:
        print(f"--- LOG SUBMITTED via POST for bot_id {bot_id} ---")
        formatted_message = log_message.model_dump_json()
        await log_manager.broadcast(bot_id, formatted_message)
        return {"status": "log received"}
    except Exception as e:
        print(f"Failed to broadcast log for bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to broadcast log message.")

# --- CRUD routes for administration ---

@router.post("/", response_model=bot_schemas.Bot, status_code=status.HTTP_201_CREATED)
def create_bot_api(bot: bot_schemas.BotCreate, db: Session = Depends(get_db)):
    """
    Creates a new bot via the API.
    """
    try:
        db_bot_check = crud_bots.get_bot_by_name(db, name=bot.name)
        if db_bot_check:
            raise HTTPException(status_code=400, detail="A bot with this name already exists.")
        
        created_bot = crud_bots.create_bot(db=db, bot=bot)
        return created_bot

    except HTTPException:
        raise
    except Exception as e:
        print("--- INTERNAL ERROR DURING BOT CREATION ---")
        print(f"Exception: {e}")
        traceback.print_exc()
        print("------------------------------------------")
        raise HTTPException(status_code=500, detail=f"Internal server error during bot creation: {e}")


@router.get("/", response_model=List[bot_schemas.Bot])
def read_bots(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieves a list of all bots (without sensitive information).
    """
    bots = crud_bots.get_bots(db, skip=skip, limit=limit)
    return bots


@router.get("/{bot_id}", response_model=bot_schemas.Bot)
def read_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves public information for a specific bot by its ID.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    return db_bot


@router.patch("/{bot_id}", response_model=bot_schemas.Bot)
def update_bot(bot_id: int, bot_update: bot_schemas.BotUpdate, db: Session = Depends(get_db)):
    """
    Updates a bot's information via the API.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    
    if bot_update.name and bot_update.name != db_bot.name:
        if crud_bots.get_bot_by_name(db, name=bot_update.name):
             raise HTTPException(status_code=400, detail="A bot with this name already exists.")

    return crud_bots.update_bot(db=db, bot_id=bot_id, bot_update=bot_update)


@router.delete("/{bot_id}", response_model=bot_schemas.Bot)
def delete_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Deletes a bot by its ID via the API.
    """
    db_bot = crud_bots.delete_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    return db_bot


@router.get("/{bot_id}/memory", response_model=bot_schemas.BotMemory, status_code=status.HTTP_200_OK)
def get_bot_memory_api(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves the memory content (documents and metadata) for a specific bot from ChromaDB.
    """
    # First, check if the bot exists in the SQL database to prevent unnecessary calls
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found in the primary database.")

    try:
        memory_content = chroma_manager.get_bot_memory(bot_id)
        if memory_content is None:
            # This could happen if ChromaDB is down or the collection fails to be accessed
            raise HTTPException(status_code=503, detail="Could not access bot memory service (ChromaDB).")
        
        return memory_content

    except Exception as e:
        print(f"--- INTERNAL ERROR DURING BOT MEMORY FETCH for bot_id {bot_id} ---")
        traceback.print_exc()
        print("---------------------------------------------------------------")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while fetching bot memory: {e}")


@router.put("/{bot_id}/mcp_servers", response_model=bot_schemas.Bot)
def update_bot_mcp_servers_associations(
    bot_id: int, 
    mcp_associations: List[mcp_schemas.MCPServerAssociationConfig], 
    db: Session = Depends(get_db)
):
    """
    Updates the association of MCP servers for a specific bot, including their configurations.
    This will replace all existing associations for the bot.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    
    # This CRUD function will be created in the next step.
    updated_bot = crud_bots.update_bot_mcp_servers(db=db, bot_id=bot_id, mcp_associations=mcp_associations)
    
    return updated_bot


# --- Specific endpoints for the Bot Launcher ---

@router.get("/{bot_id}/token", response_model=Dict[str, str])
def get_bot_token(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves just the Discord token for a specific bot.
    Used for the bot process initial startup.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail="Bot not found.")
    
    if not db_bot.discord_token:
        raise HTTPException(status_code=404, detail="Discord token not found for this bot.")
        
    return {"discord_token": db_bot.discord_token}


@router.get("/{bot_id}/config", response_model=bot_schemas.BotConfig)
async def get_bot_configuration(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves the full configuration of a bot, including its token and the global tool prompt.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if db_bot is None:
        raise HTTPException(status_code=404, detail=f"Bot with ID {bot_id} not found.")

    # CORRIGÉ: Récupérer les paramètres globaux pour obtenir le méta-prompt des outils.
    global_settings = crud_settings.get_global_settings(db)
    
    # Convertir le modèle SQLAlchemy en dictionnaire
    bot_data = db_bot.__dict__
    
    # Ajouter le méta-prompt au dictionnaire de données du bot
    bot_data['tools_system_prompt'] = global_settings.tools_system_prompt
    
    # Valider et retourner les données combinées en utilisant le schéma BotConfig
    return bot_schemas.BotConfig.model_validate(bot_data)