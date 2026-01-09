####
# FILE: app/core/llm_manager.py
####
"""
LLM Manager with support for multiple providers (Ollama, OpenAI-compatible APIs via LiteLLM)
History of changes:
- Original implementation: Ollama-only support
- 2025-01-09: Added multi-provider support using LiteLLM for OpenAI-compatible APIs
- Design choices:
  - Use LiteLLM as abstraction layer for OpenAI, Anthropic, Azure, etc.
  - Keep Ollama client for backward compatibility and performance
  - Auto-detect provider from server URL when possible
  - Support API keys for cloud providers
  - Maintain same interface for all providers
"""

import logging
import os
import threading
from datetime import datetime
from typing import List, Dict, Any, AsyncGenerator, Union, Optional
from enum import Enum

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
**Provider:** `{config.provider}`  
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

# --- Provider Enum ---
class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    GOOGLE = "google"
    COHERE = "cohere"
    MISTRAL = "mistral"
    # Generic OpenAI-compatible endpoint
    OPENAI_COMPATIBLE = "openai_compatible"
    # Auto-detect from URL
    AUTO = "auto"

class LLMConfig(BaseModel):
    """Pydantic model for a resolved LLM configuration."""
    server_url: str
    model_name: str
    context_window: int
    provider: LLMProvider = LLMProvider.AUTO
    api_key: Optional[str] = None
    custom_headers: Optional[Dict[str, str]] = None

def detect_provider_from_url(server_url: str) -> LLMProvider:
    """
    Detect the LLM provider from the server URL.
    """
    if not server_url:
        return LLMProvider.OLLAMA  # Default
    
    server_url_lower = server_url.lower()
    
    # Check for known patterns
    if "api.openai.com" in server_url_lower:
        return LLMProvider.OPENAI
    elif "api.anthropic.com" in server_url_lower:
        return LLMProvider.ANTHROPIC
    elif "openai.azure.com" in server_url_lower or "azure.com" in server_url_lower and "openai" in server_url_lower:
        return LLMProvider.AZURE_OPENAI
    elif "generativelanguage.googleapis.com" in server_url_lower or "googleapis.com" in server_url_lower and "gemini" in server_url_lower:
        return LLMProvider.GOOGLE
    elif "api.cohere.ai" in server_url_lower:
        return LLMProvider.COHERE
    elif "api.mistral.ai" in server_url_lower:
        return LLMProvider.MISTRAL
    elif "deepseek.com" in server_url_lower:
        return LLMProvider.OPENAI_COMPATIBLE
    elif "together.xyz" in server_url_lower:
        return LLMProvider.OPENAI_COMPATIBLE
    elif "api.perplexity.ai" in server_url_lower:
        return LLMProvider.OPENAI_COMPATIBLE
    elif "localhost" in server_url_lower or "127.0.0.1" in server_url_lower or "host.docker.internal" in server_url_lower:
        # Local endpoints are likely Ollama or local OpenAI-compatible servers
        if "ollama" in server_url_lower or "11434" in server_url:  # Ollama default port
            return LLMProvider.OLLAMA
        else:
            return LLMProvider.OPENAI_COMPATIBLE
    elif server_url_lower.startswith("https://"):
        # Any HTTPS endpoint is likely an OpenAI-compatible API
        return LLMProvider.OPENAI_COMPATIBLE
    else:
        # Unknown endpoint, assume OpenAI-compatible
        return LLMProvider.OPENAI_COMPATIBLE

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
            "api_key": (bot.decisional_llm_api_key, global_settings.decisional_llm_api_key),
        },
        LLM_CATEGORY_TOOLS: {
            "server_url": (bot.tools_llm_server_url, global_settings.tools_llm_server_url),
            "model_name": (bot.tools_llm_model, global_settings.tools_llm_model),
            "context_window": (bot.tools_llm_context_window, global_settings.tools_llm_context_window),
            "api_key": (bot.tools_llm_api_key, global_settings.tools_llm_api_key),
        },
        LLM_CATEGORY_OUTPUT_CLIENT: {
            "server_url": (bot.output_client_llm_server_url, global_settings.output_client_llm_server_url),
            "model_name": (bot.output_client_llm_model, global_settings.output_client_llm_model),
            "context_window": (bot.output_client_llm_context_window, global_settings.output_client_llm_context_window),
            "api_key": (bot.output_client_llm_api_key, global_settings.output_client_llm_api_key),
        }
    }

    if category not in config_map:
        raise ValueError(f"Unknown LLM category: {category}")

    category_fields = config_map[category]
    
    resolved_config = {
        key: bot_value if bot_value is not None else global_value
        for key, (bot_value, global_value) in category_fields.items()
    }

    # DEBUG: Log the resolved configuration
    logger.info(f"DEBUG resolve_llm_config: Category='{category}', Server='{resolved_config.get('server_url')}', "
                f"Model='{resolved_config.get('model_name')}', API Key Present={'Yes' if resolved_config.get('api_key') else 'No'}")
    
    # Create base config
    config = LLMConfig(**resolved_config)
    
    # Detect provider from URL if not explicitly set
    if config.provider == LLMProvider.AUTO:
        config.provider = detect_provider_from_url(config.server_url)
    
    return config

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

# --- Provider-specific client functions ---

async def _call_ollama(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """Call Ollama API."""
    try:
        client = ollama.AsyncClient(host=config.server_url)
        
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
        return response['message']['content']
        
    except ResponseError as e:
        logger.error(f"Ollama API error from '{config.server_url}': {e.status_code} - {e.error}")
        raise
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server at '{config.server_url}': {e}", exc_info=True)
        raise

async def _call_ollama_stream(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """Stream from Ollama API."""
    try:
        client = ollama.AsyncClient(host=config.server_url)
        
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
            yield chunk['message']['content']

    except ResponseError as e:
        logger.error(f"Ollama API error during stream from '{config.server_url}': {e.status_code} - {e.error}")
        error_message = f"\n\n_An error occurred with the AI model: {e.error}_"
        yield error_message
    except Exception as e:
        logger.error(f"Failed to connect to Ollama server for stream at '{config.server_url}': {e}", exc_info=True)
        error_message = "\n\n_An unexpected error occurred while generating the response._"
        yield error_message

async def _call_litellm(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """Call any LLM via LiteLLM."""
    try:
        import litellm
        from litellm import completion
        
        # Prepare messages with system prompt
        prepared_messages = _prepare_messages_for_inference(messages)
        full_messages = [{"role": "system", "content": system_prompt}] + prepared_messages
        
        # Build model string based on provider
        if config.provider == LLMProvider.OPENAI:
            model = config.model_name  # e.g., "gpt-4"
        elif config.provider == LLMProvider.ANTHROPIC:
            model = f"claude-{config.model_name}" if not config.model_name.startswith("claude-") else config.model_name
        elif config.provider == LLMProvider.AZURE_OPENAI:
            model = f"azure/{config.model_name}"
        elif config.provider == LLMProvider.GOOGLE:
            model = f"gemini/{config.model_name}"
        elif config.provider == LLMProvider.COHERE:
            model = f"cohere/{config.model_name}"
        elif config.provider == LLMProvider.MISTRAL:
            model = f"mistral/{config.model_name}"
        elif config.provider == LLMProvider.OPENAI_COMPATIBLE:
            # For custom OpenAI-compatible endpoints
            model = f"openai/{config.model_name}"
        else:
            model = config.model_name
        
        # Prepare API base and key for all providers
        extra_params = {}
        
        # Set API base for custom endpoints
        if config.server_url:
            # Different providers have different ways to specify custom endpoints
            if config.provider == LLMProvider.OPENAI_COMPATIBLE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.OPENAI:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.ANTHROPIC:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.AZURE_OPENAI:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.GOOGLE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.COHERE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.MISTRAL:
                extra_params["api_base"] = config.server_url
            else:
                # For unknown providers, try to set api_base
                extra_params["api_base"] = config.server_url
        
        # Set API key for all providers that require it
        if config.api_key:
            extra_params["api_key"] = config.api_key
        
        if config.custom_headers:
            extra_params["custom_headers"] = config.custom_headers
        
        # Add JSON mode if requested
        if json_mode:
            extra_params["response_format"] = {"type": "json_object"}
        
        # Call LiteLLM
        response = await completion(
            model=model,
            messages=full_messages,
            max_tokens=config.context_window,  # Note: context_window used as max_tokens approximation
            **extra_params
        )
        
        return response.choices[0].message.content
        
    except ImportError:
        logger.error("LiteLLM not installed. Please install with: pip install litellm")
        raise RuntimeError("LiteLLM is required for non-Ollama providers")
    except Exception as e:
        logger.error(f"LiteLLM API error: {e}", exc_info=True)
        raise

async def _call_litellm_stream(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """Stream from any LLM via LiteLLM."""
    try:
        import litellm
        from litellm import acompletion
        
        # Prepare messages with system prompt
        prepared_messages = _prepare_messages_for_inference(messages)
        full_messages = [{"role": "system", "content": system_prompt}] + prepared_messages
        
        # Build model string based on provider
        if config.provider == LLMProvider.OPENAI:
            model = config.model_name
        elif config.provider == LLMProvider.ANTHROPIC:
            model = f"claude-{config.model_name}" if not config.model_name.startswith("claude-") else config.model_name
        elif config.provider == LLMProvider.AZURE_OPENAI:
            model = f"azure/{config.model_name}"
        elif config.provider == LLMProvider.GOOGLE:
            model = f"gemini/{config.model_name}"
        elif config.provider == LLMProvider.COHERE:
            model = f"cohere/{config.model_name}"
        elif config.provider == LLMProvider.MISTRAL:
            model = f"mistral/{config.model_name}"
        elif config.provider == LLMProvider.OPENAI_COMPATIBLE:
            model = f"openai/{config.model_name}"
        else:
            model = config.model_name
        
        # Prepare API base and key for all providers
        extra_params = {}
        
        # Set API base for custom endpoints
        if config.server_url:
            # Different providers have different ways to specify custom endpoints
            if config.provider == LLMProvider.OPENAI_COMPATIBLE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.OPENAI:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.ANTHROPIC:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.AZURE_OPENAI:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.GOOGLE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.COHERE:
                extra_params["api_base"] = config.server_url
            elif config.provider == LLMProvider.MISTRAL:
                extra_params["api_base"] = config.server_url
            else:
                # For unknown providers, try to set api_base
                extra_params["api_base"] = config.server_url
        
        # Set API key for all providers that require it
        if config.api_key:
            extra_params["api_key"] = config.api_key
        
        if config.custom_headers:
            extra_params["custom_headers"] = config.custom_headers
        
        # Stream response
        response = await acompletion(
            model=model,
            messages=full_messages,
            max_tokens=config.context_window,
            stream=True,
            **extra_params
        )
        
        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
                
    except ImportError:
        logger.error("LiteLLM not installed. Please install with: pip install litellm")
        raise RuntimeError("LiteLLM is required for non-Ollama providers")
    except Exception as e:
        logger.error(f"LiteLLM streaming error: {e}", exc_info=True)
        error_message = "\n\n_An error occurred while generating the response._"
        yield error_message

# --- Model Listing Functions ---

async def list_available_models(server_url: str, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List available models from an LLM server.
    Supports both Ollama and cloud providers via LiteLLM.
    """
    try:
        # Detect provider from URL
        provider = detect_provider_from_url(server_url)
        
        if provider == LLMProvider.OLLAMA:
            # Use Ollama client
            client = ollama.AsyncClient(host=server_url)
            response = await client.list()
            models_data = response.get('models', [])
            
            # Format for consistency
            models_list = []
            for model in models_data:
                models_list.append({
                    "model": model.get("name"),
                    "size": model.get("size"),
                    "modified_at": model.get("modified_at"),
                    "digest": model.get("digest")
                })
            return models_list
            
        else:
            # Use LiteLLM for cloud providers
            import litellm
            from litellm import get_supported_openai_params
            
            # Prepare extra params
            extra_params = {}
            if api_key:
                extra_params["api_key"] = api_key
            
            # For OpenAI-compatible endpoints
            if provider == LLMProvider.OPENAI_COMPATIBLE:
                extra_params["api_base"] = server_url
            
            # Try to get models list
            # Note: LiteLLM doesn't have a direct models.list() equivalent for all providers
            # For now, return a generic model based on common patterns
            models_list = []
            
            # Common model names for different providers
            if provider == LLMProvider.OPENAI:
                models_list = [
                    {"model": "gpt-4o", "description": "OpenAI GPT-4o"},
                    {"model": "gpt-4-turbo", "description": "OpenAI GPT-4 Turbo"},
                    {"model": "gpt-4", "description": "OpenAI GPT-4"},
                    {"model": "gpt-3.5-turbo", "description": "OpenAI GPT-3.5 Turbo"},
                ]
            elif provider == LLMProvider.ANTHROPIC:
                models_list = [
                    {"model": "claude-3-opus-20240229", "description": "Anthropic Claude 3 Opus"},
                    {"model": "claude-3-sonnet-20240229", "description": "Anthropic Claude 3 Sonnet"},
                    {"model": "claude-3-haiku-20240307", "description": "Anthropic Claude 3 Haiku"},
                    {"model": "claude-2.1", "description": "Anthropic Claude 2.1"},
                ]
            elif provider == LLMProvider.GOOGLE:
                models_list = [
                    {"model": "gemini-1.5-pro", "description": "Google Gemini 1.5 Pro"},
                    {"model": "gemini-1.5-flash", "description": "Google Gemini 1.5 Flash"},
                    {"model": "gemini-pro", "description": "Google Gemini Pro"},
                ]
            elif "deepseek.com" in server_url.lower():
                # Special case for DeepSeek (detected as OPENAI_COMPATIBLE but needs specific models)
                models_list = [
                    {"model": "deepseek-chat", "description": "DeepSeek Chat"},
                    {"model": "deepseek-coder", "description": "DeepSeek Coder"},
                ]
            else:
                # Generic OpenAI-compatible
                models_list = [
                    {"model": "gpt-4", "description": "Generic GPT-4 compatible"},
                    {"model": "gpt-3.5-turbo", "description": "Generic GPT-3.5 Turbo compatible"},
                ]
            
            return models_list
            
    except Exception as e:
        logger.error(f"Failed to list models from '{server_url}': {e}", exc_info=True)
        raise

# --- Async LLM Call Functions ---

async def call_llm(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    json_mode: bool = False
) -> str:
    """
    Makes a specific, on-demand call to an LLM using the provided configuration.
    Supports multiple providers via LiteLLM.
    """
    logger.info(f"Calling LLM: Provider='{config.provider}', Server='{config.server_url}', Model='{config.model_name}', Ctx='{config.context_window}', JSON_Mode={json_mode}")
    
    try:
        # Choose the appropriate client based on provider
        if config.provider == LLMProvider.OLLAMA:
            response = await _call_ollama(config, system_prompt, messages, json_mode)
        else:
            response = await _call_litellm(config, system_prompt, messages, json_mode)
        
        # Log the interaction (using original messages for clarity)
        log_llm_interaction(config, system_prompt, messages, response, json_mode)
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to call LLM: {e}", exc_info=True)
        raise

async def call_llm_stream(
    config: LLMConfig,
    system_prompt: str,
    messages: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Makes a specific, on-demand streaming call to an LLM.
    Supports multiple providers via LiteLLM.
    """
    logger.info(f"Calling LLM Stream: Provider='{config.provider}', Server='{config.server_url}', Model='{config.model_name}', Ctx='{config.context_window}', API Key Present={'Yes' if config.api_key else 'No'}")
    
    # DEBUG: Log which client will be used
    if config.provider == LLMProvider.OLLAMA:
        logger.info(f"DEBUG: Using OLLAMA client for {config.server_url}")
    else:
        logger.info(f"DEBUG: Using LITELLM client for {config.server_url} with provider {config.provider}")
        if config.api_key:
            logger.info(f"DEBUG: API key length: {len(config.api_key)} characters")
        else:
            logger.warning(f"DEBUG: No API key provided for {config.provider}")
    
    full_response_content = ""
    try:
        # Choose the appropriate streaming client based on provider
        if config.provider == LLMProvider.OLLAMA:
            stream_generator = _call_ollama_stream(config, system_prompt, messages)
        else:
            stream_generator = _call_litellm_stream(config, system_prompt, messages)
        
        async for chunk in stream_generator:
            full_response_content += chunk
            yield chunk

    except Exception as e:
        logger.error(f"Failed during LLM streaming: {e}", exc_info=True)
        error_message = "\n\n_An unexpected error occurred while generating the response._"
        full_response_content += error_message
        yield error_message
    finally:
        # Log the full interaction after the stream is complete
        log_llm_interaction(config, system_prompt, messages, full_response_content, json_mode=False)
