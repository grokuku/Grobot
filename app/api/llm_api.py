# app/api/llm_api.py

from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Optional

from app.core.llm.ollama_client import OllamaClient

router = APIRouter(
    prefix="/llm",
    tags=["LLM Management"],
)

@router.get("/available-models", response_model=List[str])
async def get_available_models(ollama_url: Optional[str] = Query(None)):
    """
    Retrieves the list of available LLM models from an Ollama server.
    If 'ollama_url' is provided as a query parameter, it will be used.
    Otherwise, it defaults to the URL configured in the application's global settings.
    """
    try:
        # The client will use the provided host_url, or fallback to the DB settings if it's None.
        client = OllamaClient(host_url=ollama_url)

        host_to_check = await client.get_host_url()

        if not host_to_check or "host.docker.internal" in host_to_check:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The Ollama server URL is not configured or is set to a default placeholder."
            )

        models_data = await client.list_models()

        if models_data is None:
             raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach the Ollama server at '{host_to_check}'. "
                       "Check the URL and ensure the Ollama service is running."
            )
        
        model_names = [model.get("name") for model in models_data if model.get("name")]
        
        return sorted(model_names)

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error in /available-models endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {str(e)}"
        )