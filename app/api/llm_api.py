####
# FICHIER: app/api/llm_api.py
####
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

# Import correct de la fonction de listing depuis le nouveau manager
from app.core.llm_manager import list_available_models
# Imports pour l'accès à la configuration en base de données
from app.database import sql_session, crud_settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", summary="List available LLM models")
async def get_models(db: Session = Depends(sql_session.get_db)):
    """
    Fetches the list of models currently available from the configured LLM service.
    Supports both Ollama and OpenAI-compatible providers via LiteLLM.
    """
    # 1. Récupérer la configuration globale pour savoir quel serveur interroger
    settings = crud_settings.get_settings(db)
    
    # Valeurs par défaut si les settings n'existent pas encore (premier démarrage)
    server_url = "http://host.docker.internal:11434"
    api_key = None

    if settings:
        # On utilise le serveur configuré pour le LLM "décisionnel" comme référence
        if settings.decisional_llm_server_url:
            server_url = settings.decisional_llm_server_url
        if settings.decisional_llm_api_key:
            api_key = settings.decisional_llm_api_key
    
    try:
        # 2. Appel de la fonction unifiée
        # Note: Cette fonction gère automatiquement la détection Ollama vs OpenAI
        models_list = await list_available_models(server_url=server_url, api_key=api_key)
        
        # Le format de retour attendu par le frontend est souvent une liste d'objets ou de strings.
        # list_available_models retourne déjà une liste de dicts standardisée.
        return {"models": models_list}
    
    except Exception as e:
        logger.error(f"Failed to fetch models from {server_url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")