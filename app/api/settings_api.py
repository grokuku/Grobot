# app/api/settings_api.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from starlette.concurrency import run_in_threadpool

from app.database.sql_session import get_db
from app.schemas.settings_schema import GlobalSettings, GlobalSettingsUpdate, LLMModel
from app.database import crud_settings
from app.core.llm.ollama_client import list_ollama_models_async

router = APIRouter(
    prefix="/settings",
    tags=["Application Settings"]
)

@router.get("/global", response_model=GlobalSettings)
def read_global_settings(db: Session = Depends(get_db)):
    """
    Retrieves the global settings of the application.
    Creates and initializes the configuration with default values if it does not exist.
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
    Only the fields provided in the request body will be updated.
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

# UPDATED ENDPOINT
@router.get("/llm/models", response_model=List[LLMModel], tags=["Application Settings"])
async def get_ollama_models_list(
    host_url: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Fetches the list of available models from the Ollama server.
    Uses the provided 'host_url' query parameter if present, otherwise falls back to the saved global setting.
    """
    url_to_use = host_url

    if not url_to_use:
        # If no host_url is provided in the query, get it from the database
        settings = await run_in_threadpool(crud_settings.get_global_settings, db)
        if not settings or not settings.ollama_host_url:
            raise HTTPException(status_code=500, detail="Ollama host URL is not configured in global settings.")
        url_to_use = settings.ollama_host_url

    if not url_to_use:
         raise HTTPException(status_code=400, detail="Ollama host URL is missing.")

    try:
        models_data = await list_ollama_models_async(url_to_use)
        return models_data
    except Exception as e:
        # Provide a more specific error message
        detail_message = f"Could not connect to or get a valid response from Ollama server at '{url_to_use}'. Original error: {str(e)}"
        print(f"Error in get_ollama_models_list: {detail_message}")
        raise HTTPException(status_code=500, detail=detail_message)