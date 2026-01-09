from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from starlette.concurrency import run_in_threadpool
import logging

from pydantic import ValidationError

import ollama
from ollama import ResponseError

from app.database.sql_session import get_db
from app.schemas.settings_schema import (
    GlobalSettings, 
    GlobalSettingsUpdate, 
    LLMModel,
    LLMEvaluationRun,
    LLMEvaluationRunCreate,
    LLMEvaluationRunResult
)
from app.database import crud_settings
from app.worker.tasks import run_llm_evaluation

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
async def get_llm_models_list(
    host_url: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    """
    Fetches the list of available models from an LLM server.
    Supports both Ollama and cloud providers via LiteLLM.
    If host_url is not provided, it will use the decisional_llm_server_url from global settings.
    """
    url_to_use = host_url

    if not url_to_use:
        settings_orm = await run_in_threadpool(crud_settings.get_global_settings, db)
        settings = GlobalSettings.model_validate(settings_orm)
        if not settings or not settings.decisional_llm_server_url:
            raise HTTPException(status_code=500, detail="Default LLM host URL (decisional) is not configured in global settings.")
        url_to_use = str(settings.decisional_llm_server_url)

    if not url_to_use:
            raise HTTPException(status_code=400, detail="LLM host URL is missing.")

    try:
        # Import the list_available_models function
        from app.core.llm_manager import list_available_models, detect_provider_from_url
        
        # Get API key from global settings if available
        api_key = None
        if settings and settings.decisional_llm_api_key:
            api_key = str(settings.decisional_llm_api_key)
        
        # List models using the unified function
        models_data = await list_available_models(url_to_use, api_key)
        
        # Convert to LLMModel schema
        models_list = []
        for model_data in models_data:
            # Ensure the model has required fields
            model_name = model_data.get("model", "unknown")
            models_list.append(LLMModel(
                model=model_name,
                size=model_data.get("size"),
                modified_at=model_data.get("modified_at"),
                description=model_data.get("description"),
                # Note: 'digest' field is not in LLMModel schema, so we skip it
            ))
        
        return models_list

    except Exception as e:
        detail_message = f"Could not fetch models from LLM server at '{url_to_use}'. Error: {str(e)}"
        logger.warning(detail_message)
        raise HTTPException(status_code=500, detail=detail_message)


@router.post(
    "/llm/evaluate",
    response_model=LLMEvaluationRun,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Application Settings"]
)
async def start_llm_evaluation(
    evaluation_request: LLMEvaluationRunCreate,
    db: Session = Depends(get_db)
):
    """
    Starts a background task to evaluate an LLM's performance.
    """
    logger.info(f"Received request to evaluate LLM: {evaluation_request.llm_model_name} on server {evaluation_request.llm_server_url} with context window {evaluation_request.llm_context_window}")
    
    try:
        # 1. Start the background Celery task
        # --- CORRECTED ---
        # The task expects a single dictionary argument named 'evaluation_request_data'.
        task = run_llm_evaluation.delay(
            evaluation_request_data=evaluation_request.model_dump()
        )
        logger.info(f"Celery task for LLM evaluation started with ID: {task.id}")
        
    except Exception as e:
        logger.error(f"Failed to start Celery task for LLM evaluation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not start the evaluation task. Please check the Celery worker and broker status."
        )
        
    try:
        # 2. Create the record in the database
        db_run = crud_settings.create_llm_evaluation_run(
            db=db,
            evaluation_data=evaluation_request,
            task_id=task.id
        )
        
        logger.info(f"LLM evaluation run for task {task.id} saved to database.")
        
        return db_run
        
    except Exception as e:
        logger.error(f"Failed to save LLM evaluation run to database for task {task.id}: {e}", exc_info=True)
        # Here we might want to consider revoking the Celery task, but for now, we'll just report the error.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation task was started but failed to be saved to the database."
        )


@router.get(
    "/llm/evaluations/{llm_category}",
    response_model=List[LLMEvaluationRunResult],
    tags=["Application Settings"]
)
def get_llm_evaluation_results(
    llm_category: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves the history of LLM evaluation runs for a specific category.
    """
    logger.info(f"Fetching evaluation results for category: {llm_category}")
    try:
        results = crud_settings.get_llm_evaluation_runs_by_category(db, llm_category)
        return results
    except Exception as e:
        logger.error(f"Failed to retrieve evaluation results for category {llm_category}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching evaluation results."
        )