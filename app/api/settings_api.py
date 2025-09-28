from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from starlette.concurrency import run_in_threadpool
import logging

import ollama
from ollama import ResponseError

from app.database.sql_session import get_db
from app.schemas.settings_schema import GlobalSettings, GlobalSettingsUpdate, LLMModel
from app.database import crud_settings

router = APIRouter(
    prefix="/settings",
    tags=["Application Settings"]
)
logger = logging.getLogger(__name__)

@router.get("/global", response_model=GlobalSettings)
def read_global_settings(db: Session = Depends(get_db)):
    """
    Retrieves the global settings of the application.
    """
    try:
        settings = crud_settings.get_global_settings(db)
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error while retrieving global settings: {e}"
        )


@router.patch("/global", response_model=GlobalSettings)
def patch_global_settings(
    settings_update: GlobalSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates the global settings of the application.
    """
    try:
        updated_settings = crud_settings.save_global_settings(db=db, settings_update=settings_update)
        return updated_settings
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred while updating settings: {e}"
        )


# =================================================================
#          *** CORRECTION FINALE DU BUG D'AFFICHAGE ***
# =================================================================
@router.get(
    "/llm/models", 
    response_model=List[LLMModel],
    # On force FastAPI à utiliser les noms de champs du modèle ('name') 
    # pour la réponse JSON, et non les alias ('model').
    response_model_by_alias=False,
    tags=["Application Settings"]
)
async def get_ollama_models_list(
    host_url: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Fetches the list of available models from the Ollama server.
    """
    url_to_use = host_url

    if not url_to_use:
        settings = await run_in_threadpool(crud_settings.get_global_settings, db)
        if not settings or not settings.ollama_host_url:
            raise HTTPException(status_code=500, detail="Ollama host URL is not configured in global settings.")
        url_to_use = str(settings.ollama_host_url)

    if not url_to_use:
            raise HTTPException(status_code=400, detail="Ollama host URL is missing.")

    try:
        temp_client = ollama.AsyncClient(host=url_to_use)
        # La librairie retourne un objet réponse qui contient la liste dans un champ 'models'.
        models_data = await temp_client.list()
        
        models_list = models_data.get('models', [])
        return [LLMModel.model_validate(model) for model in models_list]

    except ResponseError as e:
        detail_message = f"Ollama API error from host '{url_to_use}'. Error: {str(e.error)}"
        logger.warning(detail_message)
        raise HTTPException(status_code=500, detail=detail_message)
    except Exception as e:
        detail_message = f"Could not connect to Ollama server at '{url_to_use}'. Please check the URL and ensure Ollama is running. Error: {str(e)}"
        logger.warning(detail_message)
        raise HTTPException(status_code=500, detail=detail_message)