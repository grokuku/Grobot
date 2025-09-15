import requests
import httpx
import json
import logging
from contextlib import contextmanager
from typing import Optional, AsyncGenerator, List, Dict, Any

from app.database.sql_session import SessionLocal
from app.database.crud_settings import get_global_settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - (OLLAMA_CLIENT) - %(message)s')

DEFAULT_OLLAMA_HOST = "http://host.docker.internal:11434"

async def list_ollama_models_async(host_url: str) -> List[dict]:
    """
    Fetches the list of available models from the Ollama server API.
    """
    if not host_url:
        logging.error("Ollama host URL is not provided.")
        return []

    api_url = f"{host_url.rstrip('/')}/api/tags"
    timeout_config = httpx.Timeout(60.0, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
    except httpx.RequestError as e:
        logging.error(f"Communication error with Ollama API ({api_url}): {e}")
        raise
    except httpx.HTTPStatusError as e:
        logging.error(f"Ollama API returned an error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error while fetching Ollama models: {e}")
        raise


@contextmanager
def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class OllamaClient:
    def __init__(self, host_url: Optional[str] = None):
        self.host = host_url if host_url else self._get_global_ollama_host()

    def _get_global_ollama_host(self) -> str:
        """Retrieves the Ollama URL from the new global settings."""
        with get_db_session() as db:
            global_settings = get_global_settings(db)
            if global_settings and global_settings.ollama_host_url:
                # Ensure the host is using the service name for container-to-container communication
                return str(global_settings.ollama_host_url).replace("localhost", "ollama").replace("host.docker.internal", "ollama")
        return DEFAULT_OLLAMA_HOST.replace("host.docker.internal", "ollama") # Fallback as well

    # --- MÉTHODE RESTAURÉE POUR COMPATIBILITÉ AVEC llm_api.py ---
    async def get_host_url(self) -> str:
        """Returns the configured host URL."""
        return self.host

    async def chat_response(
        self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None, format: str = ""
    ) -> Dict[str, Any]:
        """
        Calls the /api/chat endpoint of Ollama for a single, non-streaming response.
        """
        if not self.host:
            raise ConnectionError("Ollama host URL is not configured.")

        api_url = f"{self.host.rstrip('/')}/api/chat"
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        
        if tools:
            payload["tools"] = tools
        if format:
            payload["format"] = format
        
        logging.info(f"Sending this non-streaming payload to Ollama:\n{json.dumps(payload, indent=2)}")
        timeout_config = httpx.Timeout(300.0, connect=60.0)

        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(api_url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            logging.error(f"Communication error with Ollama API ({api_url}): {e}")
            raise
        except httpx.HTTPStatusError as e:
            logging.error(f"Ollama API returned an error: {e.response.status_code} - {e.response.text}")
            raise

    async def chat_streaming_response(
        self, model: str, messages: List[Dict], tools: Optional[List[Dict]] = None, context_window: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Calls the /api/chat endpoint of Ollama with explicit, robust timeout for a streaming response.
        """
        if not self.host:
            error_msg = json.dumps({"error": "Ollama host URL is not configured.", "done": True})
            yield error_msg
            return

        api_url = f"{self.host.rstrip('/')}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        
        if tools:
            payload["tools"] = tools
        
        if context_window:
            payload["options"] = {"num_ctx": context_window}

        logging.info(f"Sending this streaming payload to Ollama:\n{json.dumps(payload, indent=2)}")
        timeout_config = httpx.Timeout(300.0, connect=60.0)

        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                async with client.stream("POST", api_url, json=payload) as response:
                    try:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            yield line
                    except httpx.HTTPStatusError as e:
                        error_body = await response.aread()
                        error_message = f"Ollama API returned an error: {e.response.status_code} - {error_body.decode().strip()}"
                        logging.error(f"[OllamaClient] {error_message}")
                        yield json.dumps({"error": error_message, "done": True})
        
        except httpx.RequestError as e:
            error_message = f"Communication error with Ollama API ({api_url}): {e}"
            logging.error(error_message)
            yield json.dumps({"error": error_message, "done": True})
        except Exception as e:
            error_message = f"Unexpected error during streaming from Ollama: {e}"
            logging.error(error_message)
            yield json.dumps({"error": error_message, "done": True})

    async def list_models(self) -> List[dict]:
        """
        Fetches the list of available models using the standalone function.
        """
        return await list_ollama_models_async(self.host)