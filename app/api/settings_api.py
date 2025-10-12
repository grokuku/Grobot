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