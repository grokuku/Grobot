# app/core/llm_manager.py
import logging
from typing import List, Dict, Any, AsyncGenerator

import ollama
from ollama import ResponseError
from pydantic import BaseModel

# MODIFIED: Added prompts to be accessible from the manager
from app.core.agents import prompts
from app.database.sql_models import Bot, GlobalSettings

logger = logging.getLogger(__name__)

# --- Constants for LLM Categories ---
LLM_CATEGORY_DECISIONAL = "decisional"
LLM_CATEGORY_TOOLS = "tools"
LLM_CATEGORY_OUTPUT_CLIENT = "output_client"

class LLMConfig(BaseModel):
    """Pydantic model for a resolved LLM configuration."""
    server_url: str
    model_name: str
    context_window: int

def resolve_llm_config(
    bot: Bot,
    global_settings: GlobalSettings,
    category: str
) -> LLMConfig:
    """
    Resolves the LLM configuration for a given category by checking bot-specific
    settings first, then falling back to global settings.
    """
    config_map = {
        LLM_CATEGORY_DECISIONAL: {
            "server_url": (bot.decisional_llm_server_url, global_settings.decisional_llm_server_url),
            "model_name": (bot.decisional_llm_model, global_settings.decisional_llm_model),
            "context_window": (bot.decisional_llm_context_window, global_settings.decisional_llm_context_window),
        },
        LLM_CATEGORY_TOOLS: {
            "server_url": (bot.tools_llm_server_url, global_settings.tools_llm_server_url),
            "model_name": (bot.tools_llm_model, global_settings.tools_llm_model),
            "context_window": (bot.tools_llm_context_window, global_settings.tools_llm_context_window),
        },
        LLM_CATEGORY_OUTPUT_CLIENT: {
            "server_url": (bot.output_client_llm_server_url, global_settings.output_client_llm_server_url),
            "model_name": (bot.output_client_llm_model, global_settings.output_client_llm_model),
            "context_window": (bot.output_client_llm_context_window, global_settings.output_client_llm_context_window),
        }
    }

    if category not in config_map:
        raise ValueError(f"Unknown LLM category: {category}")

    category_fields = config_map[category]
    
    resolved_config = {
        key: bot_value if bot_value is not None else global_value
        for key, (bot_value, global_value) in category_fields.items()
    }

    return LLMConfig(**resolved_config)

async def call_llm(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """
    Makes a specific, on-demand call to an Ollama server using the provided configuration.
    """
    logger.info(f"Calling LLM: Server='{config.server_url}', Model='{config.model_name}', JSON_Mode={json_mode}")
    try:
        client = ollama.AsyncClient(host=config.server_url)
        
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
        request_params = {
            "model": config.model_name,
            "messages": full_messages,
        }
        if json_mode:
            request_params["format"] = "json"

        response = await client.chat(**request_params)
        return response['message']['content']
        
    except ResponseError as e:
        logger.error(f"Ollama API error from '{config.server_url}': {e.status_code} - {e.error}")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server at '{config.server_url}': {e}", exc_info=True)
        raise

# NEW: Added function for streaming responses
async def call_llm_stream(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Makes a specific, on-demand streaming call to an Ollama server.
    """
    logger.info(f"Calling LLM Stream: Server='{config.server_url}', Model='{config.model_name}'")
    try:
        client = ollama.AsyncClient(host=config.server_url)
        
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        
        request_params = {
            "model": config.model_name,
            "messages": full_messages,
        }

        async for chunk in await client.chat(**request_params, stream=True):
            yield chunk['message']['content']

    except ResponseError as e:
        logger.error(f"Ollama API error during stream from '{config.server_url}': {e.status_code} - {e.error}")
        yield f"\n\n_An error occurred with the AI model: {e.error}_"
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server for stream at '{config.server_url}': {e}", exc_info=True)
        yield "\n\n_An unexpected error occurred while generating the response._"