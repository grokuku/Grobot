####
# FILE: app/core/llm_manager.py
####
import logging
import os
import threading
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator, Union

import ollama
from ollama import ResponseError
from pydantic import BaseModel

# MODIFIED: Added prompts to be accessible from the manager
from app.core.agents import prompts
from app.database.sql_models import Bot, GlobalSettings

logger = logging.getLogger(__name__)

# --- LLM Interaction Logging Setup ---
LOG_DIR = "/app/logs"
LOG_FILE = os.path.join(LOG_DIR, "llm_interactions.md")
log_lock = threading.Lock()

# Ensure the log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def log_llm_interaction(config: 'LLMConfig', system_prompt: str, messages: List[Dict[str, Any]], response: Union[str, Dict[str, Any]], json_mode: bool):
    """
    Logs the complete LLM interaction to a Markdown file.
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Combine system prompt and user messages for the final prompt
        full_prompt_content = system_prompt
        for message in messages:
            # CORRECTED: Handle both dict and potential Pydantic object for robustness
            if isinstance(message, dict):
                role = message.get("role", "unknown")
                name = message.get("name")
                content = message.get("content", "")
            else: # Assuming Pydantic model or object with attributes
                role = getattr(message, "role", "unknown")
                name = getattr(message, "name", None)
                content = getattr(message, "content", "")

            role_header = role.upper()
            if name:
                role_header += f" ({name})"
            
            full_prompt_content += f"\n\n--- {role_header} ---\n{content}"
        
        # CORRECTED: Properly extract the response content
        response_content = ""
        if isinstance(response, dict):
            # This case is for non-streaming responses from client.chat()
            response_content = response.get('message', {}).get('content', str(response))
        elif isinstance(response, str):
            # This case is for the full response from a stream
            response_content = response
        else:
            # Fallback for unexpected types
            response_content = str(response)

        log_entry = f"""---

**Timestamp:** {timestamp}  
**Model:** `{config.model_name}`  
**JSON Mode:** `{'Yes' if json_mode else 'No'}`
**Context Window:** `{config.context_window}`

#### PROMPT

{full_prompt_content.strip()}

#### RESPONSE

{response_content.strip()}

---
"""

        with log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_entry)

    except Exception as e:
        logger.error(f"Failed to write to LLM interaction log: {e}", exc_info=True)

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

# --- NEW: Message Preparation Helper ---

def _prepare_messages_for_inference(messages: List[Union[Dict[str, Any], BaseModel]]) -> List[Dict[str, Any]]:
    """
    Prepares messages for the LLM by explicitly injecting the sender's name AND ID into the content.
    This ensures that the model can distinguish between different users and maintains persistence
    even if a user changes their display name.
    """
    prepared_messages = []
    for msg in messages:
        # Normalize to dict and create a copy to avoid side effects
        msg_dict = msg.model_dump() if isinstance(msg, BaseModel) else msg.copy()
        
        # Inject name and ID into content if present and role is user
        if msg_dict.get("role") == "user":
            name = msg_dict.get("name", "Unknown User")
            user_id = msg_dict.get("user_id")
            original_content = msg_dict.get("content", "")
            
            # Format: "Name (ID: 12345): Message" or "Name: Message"
            if user_id:
                msg_dict["content"] = f"{name} (ID: {user_id}): {original_content}"
            else:
                msg_dict["content"] = f"{name}: {original_content}"
            
            # Remove metadata keys to keep the payload clean for Ollama
            msg_dict.pop("name", None)
            msg_dict.pop("user_id", None)
            
        prepared_messages.append(msg_dict)
    return prepared_messages

# --- Async LLM Call Functions ---

async def call_llm(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """
    Makes a specific, on-demand call to an Ollama server using the provided configuration.
    """
    logger.info(f"Calling LLM: Server='{config.server_url}', Model='{config.model_name}', Ctx='{config.context_window}', JSON_Mode={json_mode}")
    try:
        client = ollama.AsyncClient(host=config.server_url)
        
        # PREPARE MESSAGES: Inject names/IDs into content for context awareness
        prepared_messages = _prepare_messages_for_inference(messages)
        full_messages = [{"role": "system", "content": system_prompt}] + prepared_messages
        
        request_params = {
            "model": config.model_name,
            "messages": full_messages,
            "options": {
                "num_ctx": config.context_window
            }
        }
        if json_mode:
            request_params["format"] = "json"

        response = await client.chat(**request_params)
        
        # Log the interaction (using original messages for clarity)
        log_llm_interaction(config, system_prompt, messages, response, json_mode)
        
        return response['message']['content']
        
    except ResponseError as e:
        logger.error(f"Ollama API error from '{config.server_url}': {e.status_code} - {e.error}")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server at '{config.server_url}': {e}", exc_info=True)
        raise

async def call_llm_stream(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Makes a specific, on-demand streaming call to an Ollama server.
    """
    logger.info(f"Calling LLM Stream: Server='{config.server_url}', Model='{config.model_name}', Ctx='{config.context_window}'")
    full_response_content = ""
    try:
        logger.debug(f"Initializing Ollama chat stream for model {config.model_name}...")
        client = ollama.AsyncClient(host=config.server_url)
        
        # PREPARE MESSAGES: Inject names/IDs into content for context awareness
        prepared_messages = _prepare_messages_for_inference(messages)
        full_messages = [{"role": "system", "content": system_prompt}] + prepared_messages
        
        request_params = {
            "model": config.model_name,
            "messages": full_messages,
            "options": {
                "num_ctx": config.context_window
            }
        }

        async for chunk in await client.chat(**request_params, stream=True):
            chunk_content = chunk['message']['content']
            full_response_content += chunk_content
            yield chunk_content

    except ResponseError as e:
        logger.error(f"Ollama API error during stream from '{config.server_url}': {e.status_code} - {e.error}")
        error_message = f"\n\n_An error occurred with the AI model: {e.error}_"
        full_response_content += error_message
        yield error_message
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server for stream at '{config.server_url}': {e}", exc_info=True)
        error_message = "\n\n_An unexpected error occurred while generating the response._"
        full_response_content += error_message
        yield error_message
    finally:
        # Log the full interaction after the stream is complete
        log_llm_interaction(config, system_prompt, messages, full_response_content, json_mode=False)