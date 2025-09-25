# app/main.py

print("--- CHARGEMENT DE app/main.py (VERSION AVEC LOGGING MIDDLEWARE) ---")

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
import time

from app.api import bots_api, chat_api, llm_api, files_api
from app.api import settings_api, mcp_api, tools_api, user_profiles_api
from app.database import sql_models
from app.database.sql_session import engine
import logging

logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)


def create_db_and_tables():
    """
    Crée toutes les tables de la base de données si elles n'existent pas déjà.
    """
    print("Vérification et création des tables de la base de données...")
    try:
        sql_models.Base.metadata.create_all(bind=engine)
        print("Vérification/création des tables terminée.")
    except Exception as e:
        print(f"Une erreur est survenue lors de la création des tables : {e}")
        raise

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gère le cycle de vie de l'application.
    """
    print("Démarrage de l'application API...")
    create_db_and_tables()
    yield
    print("Arrêt de l'application API.")

app = FastAPI(
    title="GroBot API",
    description="L'API backend pour la plateforme GroBot.",
    version="0.4.0-mcp",
    lifespan=lifespan
)

# --- Middleware de logging des requêtes ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Intercepte chaque requête pour en logger les détails.
    Ceci est un outil de débogage crucial.
    """
    start_time = time.time()
    # On ignore les logs pour l'endpoint de health check pour ne pas polluer les logs
    if request.url.path != "/health":
        print(f"--> REQUÊTE ENTRANTE: {request.method} {request.url}")
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    if request.url.path != "/health":
        print(f"<-- RÉPONSE SORTANTE: {response.status_code} (Traité en {process_time:.4f}s)")
    
    return response


# --- Configuration du CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Création d'un routeur global pour le versionnage de l'API ---
api_v1_router = APIRouter(prefix="/api")

# --- Inclusion des routeurs de l'API ---
# Les endpoints de log (POST et WebSocket) sont maintenant gérés
# exclusivement par le routeur de bots_api.
api_v1_router.include_router(bots_api.router)
api_v1_router.include_router(chat_api.router)
api_v1_router.include_router(llm_api.router)
api_v1_router.include_router(files_api.router)
api_v1_router.include_router(settings_api.router)
api_v1_router.include_router(mcp_api.router)
api_v1_router.include_router(tools_api.router)
api_v1_router.include_router(user_profiles_api.router)
# NOUVEAU: Inclusion du routeur admin pour la recherche globale d'utilisateurs.
# Il est défini dans user_profiles_api.py avec un préfixe "/users".
# L'URL finale sera donc /api/users/search.
api_v1_router.include_router(user_profiles_api.router_admin)


# Inclusion du routeur principal versionné dans l'application
app.include_router(api_v1_router)

@app.get("/health", tags=["Monitoring"])
def health_check():
    """
    Endpoint de test pour vérifier que l'API est en ligne et fonctionnelle.
    """
    return {"status": "ok"}


@app.get("/", tags=["Root"])
async def read_root():
    """
    Endpoint racine pour donner un message de bienvenue.
    """
    return {"message": "Bienvenue sur l'API GroBot"}