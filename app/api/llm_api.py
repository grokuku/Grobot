import logging
from fastapi import APIRouter, HTTPException
from ollama import ResponseError

# On importe le module entier, pas une classe spécifique
from app.core.llm import ollama_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/models", summary="List available Ollama models")
async def get_models():
    """
    Fetches the list of models currently available from the Ollama service.
    """
    # On accède au client via le llm_manager
    client = ollama_client.llm_manager.get("client")
    if not client:
        raise HTTPException(status_code=503, detail="Ollama client is not initialized. Please configure the Ollama host in the global settings.")
    
    try:
        # On appelle la méthode 'list' du client ollama directement
        models = await client.list()
        return models
    except ResponseError as e:
        logger.error(f"Failed to fetch models from Ollama: {e.error}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch models from Ollama: {e.error}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")