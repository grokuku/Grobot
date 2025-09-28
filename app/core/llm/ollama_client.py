import logging
from typing import List, Dict, Any, AsyncGenerator

import ollama
from ollama import ResponseError
from sqlalchemy.orm import Session

from app.database import crud_settings

logger = logging.getLogger(__name__)

# --- Shared State for LLM Client ---
# MODIFICATION 1: On supprime le fallback codé en dur.
llm_manager: Dict[str, Any] = {"client": None, "model": None}

async def initialize_llm_client(db: Session):
    """
    Fetches Ollama settings from the database and initializes the shared client.
    This function should be called during the FastAPI application's startup event.
    """
    logger.info("Attempting to initialize Ollama client...")
    try:
        global_settings = crud_settings.get_global_settings(db)
        if global_settings and global_settings.ollama_host_url:
            llm_manager["client"] = ollama.AsyncClient(host=str(global_settings.ollama_host_url))
            if global_settings.default_llm_model:
                llm_manager["model"] = global_settings.default_llm_model
            
            # MODIFICATION 2: Log plus clair et gestion du cas où le modèle n'est pas défini.
            if llm_manager["model"]:
                logger.info(f"Ollama client initialized for host: {global_settings.ollama_host_url} with model: {llm_manager['model']}")
            else:
                logger.warning(f"Ollama client initialized for host: {global_settings.ollama_host_url} but NO default model is configured in the database.")
        else:
            logger.warning("Ollama settings not found in database. LLM client not initialized.")
    except Exception as e:
        logger.critical(f"Failed to initialize Ollama client from database settings: {e}", exc_info=True)

async def _get_current_model() -> str:
    """Helper to get the currently configured model and ensure it's set."""
    model = llm_manager.get("model")
    if not model:
        raise RuntimeError("Ollama default model is not configured. Please set it in the global settings.")
    return model

async def _call_ollama_chat(
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """Private helper function to make a generic call to the Ollama chat endpoint."""
    client = llm_manager.get("client")
    if not client:
        raise RuntimeError("Ollama client is not initialized. Check database settings.")

    model_to_use = await _get_current_model()
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    request_params = {
        "model": model_to_use,
        "messages": full_messages,
    }
    if json_mode:
        request_params["format"] = "json"

    try:
        response = await client.chat(**request_params)
        return response['message']['content']
    except ResponseError as e:
        logger.error(f"Ollama API error: {e.status_code} - {e.error}")
        raise

async def get_llm_json_response(system_prompt: str, messages: List[Dict[str, Any]]) -> str:
    """Calls the Ollama model with a request for a JSON-formatted response."""
    logger.debug("Requesting JSON response from LLM.")
    return await _call_ollama_chat(system_prompt, messages, json_mode=True)

async def get_llm_response(system_prompt: str, messages: List[Dict[str, Any]]) -> str:
    """Calls the Ollama model for a standard, plain text response."""
    logger.debug("Requesting text response from LLM.")
    return await _call_ollama_chat(system_prompt, messages, json_mode=False)

async def get_llm_response_stream(
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Calls the Ollama model for a streamed response, yielding chunks of text.
    """
    logger.debug("Requesting streamed text response from LLM.")
    client = llm_manager.get("client")
    if not client:
        raise RuntimeError("Ollama client is not initialized. Check database settings.")

    model_to_use = await _get_current_model()
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    request_params = {
        "model": model_to_use,
        "messages": full_messages,
    }

    try:
        async for chunk in await client.chat(**request_params, stream=True):
            yield chunk['message']['content']
    except ResponseError as e:
        logger.error(f"Ollama API error during stream: {e.status_code} - {e.error}")
        yield f"\n\n_An error occurred with the AI model: {e.error}_"
    except Exception as e:
        logger.error(f"An unexpected error occurred during LLM stream: {e}", exc_info=True)
        yield "\n\n_An unexpected error occurred while generating the response._"