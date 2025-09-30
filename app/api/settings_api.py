# Fichier: app/api/settings_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from starlette.concurrency import run_in_threadpool
import logging

from pydantic import ValidationError

import ollama
from ollama import ResponseError

from app.database.sql_session import get_db
# NOTE: LLMModel is no longer directly imported as it's part of the settings_schema
from app.schemas.settings_schema import GlobalSettings, GlobalSettingsUpdate, LLMModel
from app.database import crud_settings

router = APIRouter(
    prefix="/settings",
    tags=["Application Settings"]
)
logger = logging.getLogger(__name__)

@router.get("/global", response_model=GlobalSettings, response_model_by_alias=True)
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


@router.patch("/global", response_model=GlobalSettings, response_model_by_alias=True)
def patch_global_settings(
    settings_update: GlobalSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates the global settings of the application.
    """
    # NEW: Log the received and parsed payload to see what the API is working with.
    logger.info(f">>> [API SAVE] Received settings update request. Payload: {settings_update.model_dump_json(by_alias=False, exclude_unset=True)}")
    try:
        updated_settings = crud_settings.save_global_settings(db=db, settings_update=settings_update)
        return updated_settings
    except ValidationError as e:
        logger.error(f"Pydantic validation failed during settings update: {e.json()}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred while updating settings: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {str(e)}"
        )


@router.get(
    "/llm/models", 
    response_model=List[LLMModel],
    response_model_by_alias=True,
    tags=["Application Settings"]
)
async def get_ollama_models_list(
    host_url: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Fetches the list of available models from the Ollama server.
    If host_url is not provided, it will use the decisional_llm_server_url from global settings.
    """
    url_to_use = host_url

    if not url_to_use:
        settings_orm = await run_in_threadpool(crud_settings.get_global_settings, db)
        settings = GlobalSettings.model_validate(settings_orm)
        if not settings or not settings.decisional_llm_server_url:
            raise HTTPException(status_code=500, detail="Default Ollama host URL (decisional) is not configured in global settings.")
        url_to_use = str(settings.decisional_llm_server_url)

    if not url_to_use:
            raise HTTPException(status_code=400, detail="Ollama host URL is missing.")

    try:
        temp_client = ollama.AsyncClient(host=url_to_use)
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