####
# FICHIER: app/main.py
####
import logging
import json # <-- ADDED
from contextlib import asynccontextmanager
import asyncio 

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect # <-- MODIFIED
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
from app.core.websocket_manager import websocket_manager # <-- ADDED
from app.database import sql_session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("--- CHARGEMENT DE app/main.py (VERSION AVEC LIFESPAN ET INIT LLM) ---")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Logique de Démarrage ---
    logger.info("Application startup...")
    
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
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    return response


# --- WebSocket Endpoint ---
@app.websocket("/ws/bots/{bot_id}")
async def websocket_endpoint(websocket: WebSocket, bot_id: int):
    await websocket_manager.connect(bot_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket message from bot {bot_id}: {data}")

            # Check if this message is a response to a pending request
            if "request_id" in data and "response" in data:
                websocket_manager.resolve_request(data["request_id"], data["response"])
            else:
                # Handle other types of incoming messages if needed in the future
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


# --- Static Files ---
# MODIFICATION : Suppression de cette ligne. Le service des fichiers statiques
# est la responsabilité de Nginx dans cette architecture, pas de FastAPI.
# app.mount("/", StaticFiles(directory="/app/src", html=True), name="static")


# --- Exception Handlers ---
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception for {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "An unexpected server error occurred."},
    )