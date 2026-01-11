####
# FICHIER: app/main.py
####
import logging
import json
from contextlib import asynccontextmanager
import asyncio 

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    bots_api,
    chat_api,
    llm_api,
    files_api,
    mcp_api,
    settings_api,
    user_profiles_api,
    tools_api,
    workflows_api
)
from app.api.mcp_api import background_discovery_task
from app.core.websocket_manager import websocket_manager
from app.database import sql_session
from app.database.sql_session import engine

# --- NOUVEAU : Import du gestionnaire de migration ---
from app.database import migration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("--- CHARGEMENT DE app/main.py (VERSION MIGRATION ROBUSTE) ---")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Logique de Démarrage ---
    logger.info("Application startup...")
    
    # --- GESTION DE LA BASE DE DONNÉES (STRATÉGIE BLUE/GREEN) ---
    try:
        logger.info("Vérification du schéma de la base de données...")
        
        # On délègue toute la logique complexe au module de migration.
        # Il va vérifier la version, et si nécessaire : renommage (backup), create_all, import data.
        migration.migrate_if_needed(engine)
        
        logger.info("Base de données prête et opérationnelle.")
    except Exception as e:
        logger.critical(f"CRITICAL DATABASE ERROR DURING MIGRATION: {e}")
        # Si la migration échoue, il vaut mieux arrêter l'appli pour ne pas corrompre plus de données
        raise e

    logger.info("Starting background task for MCP tool discovery...")
    asyncio.create_task(background_discovery_task())
    
    yield
    
    # --- Logique d'Arrêt ---
    logger.info("Application shutdown...")


app = FastAPI(lifespan=lifespan)

# --- Middlewares ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    return response


# --- WebSocket Endpoint ---
@app.websocket("/ws/bots/{bot_id}")
async def websocket_endpoint(websocket: WebSocket, bot_id: int):
    await websocket_manager.connect(bot_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if "request_id" in data and "response" in data:
                websocket_manager.resolve_request(data["request_id"], data["response"])
            else:
                logger.warning(f"Unhandled WebSocket message from bot {bot_id}: {data}")

    except WebSocketDisconnect:
        websocket_manager.disconnect(bot_id)
    except Exception as e:
        logger.error(f"Error in WebSocket for bot {bot_id}: {e}", exc_info=True)
        websocket_manager.disconnect(bot_id)


# --- API Routers ---
app.include_router(bots_api.router, prefix="/api", tags=["bots"])
app.include_router(chat_api.router, prefix="/api/chat", tags=["chat"])
app.include_router(llm_api.router, prefix="/api/llm", tags=["llm"])
app.include_router(files_api.router, prefix="/api", tags=["files"])
app.include_router(mcp_api.router, prefix="/api", tags=["mcp"])
app.include_router(settings_api.router, prefix="/api", tags=["settings"])
app.include_router(user_profiles_api.router, prefix="/api", tags=["user_profiles"])
app.include_router(tools_api.router, prefix="/api", tags=["tools"])
app.include_router(workflows_api.router, prefix="/api", tags=["workflows"])


# --- Exception Handlers ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected server error occurred."},
    )