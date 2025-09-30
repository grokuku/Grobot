import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# === MODIFICATION START: Import tools_api ===
from app.api import (
    bots_api,
    chat_api,
    llm_api,
    files_api,
    mcp_api,
    settings_api,
    user_profiles_api,
    tools_api
)
# === MODIFICATION END ===
from app.database import sql_session
# REMOVED: from app.core.llm import ollama_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("--- CHARGEMENT DE app/main.py (VERSION AVEC LIFESPAN ET INIT LLM) ---")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Logique de Démarrage ---
    logger.info("Application startup...")
    # REMOVED: The llm_manager is stateless and does not require initialization.
    # db = next(sql_session.get_db())
    # try:
    #     await ollama_client.initialize_llm_client(db)
    # finally:
    #     db.close()
    
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


# --- API Routers ---
app.include_router(bots_api.router, prefix="/api", tags=["bots"])
app.include_router(chat_api.router, prefix="/api/chat", tags=["chat"])
app.include_router(llm_api.router, prefix="/api/llm", tags=["llm"])
app.include_router(files_api.router, prefix="/api", tags=["files"])
app.include_router(mcp_api.router, prefix="/api", tags=["mcp"])
app.include_router(settings_api.router, prefix="/api", tags=["settings"])
app.include_router(user_profiles_api.router, prefix="/api", tags=["user_profiles"])
# === MODIFICATION START: Include the tools router ===
app.include_router(tools_api.router, prefix="/api", tags=["tools"])
# === MODIFICATION END ===


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