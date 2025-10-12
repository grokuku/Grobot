import logging
import json
from typing import List, Dict, Any, Optional, AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

# Timeout for API requests in seconds.
# 300 seconds (5 minutes) to allow for long tool execution times (e.g., image generation).
API_TIMEOUT = 300.0

class APIClient:
    """
    A client for interacting with the GroBot backend API.

    This class manages a persistent HTTP session for improved performance
    and encapsulates all API call logic.
    """
    def __init__(self, base_url: str, bot_id: int):
        self._base_url = base_url.rstrip('/')
        self._bot_id = bot_id
        self._client = httpx.AsyncClient(timeout=API_TIMEOUT)
        self._bot_settings: Optional[Dict[str, Any]] = None # Cache for bot settings
        logger.info(f"APIClient initialized for bot_id {self._bot_id} at {self._base_url}")

    async def close(self):
        """Closes the underlying HTTP client session."""
        await self._client.aclose()
    
    async def get_bot_settings(self) -> Dict[str, Any]:
        """
        Fetches bot settings from the API and caches the result.
        Returns an empty dict on failure.
        """
        if self._bot_settings is not None:
            return self._bot_settings
        
        url = f"{self._base_url}/api/bots/{self._bot_id}"
        logger.info(f"Fetching settings for bot {self._bot_id} for the first time.")
        try:
            response = await self._client.get(url, timeout=10.0)
            response.raise_for_status()
            self._bot_settings = response.json()
            return self._bot_settings
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get bot settings, status {e.response.status_code}: {e.response.text}")
            return {}
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"An error occurred while requesting bot settings: {e}")
            return {}
        except Exception as e:
            logger.error(f"An unexpected error occurred in get_bot_settings: {e}", exc_info=True)
            return {}

    async def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Fetches all tool definitions for the bot from the backend API.
        Used for autocompletion in slash commands.
        """
        url = f"{self._base_url}/api/tools/definitions"
        params = {"bot_id": self._bot_id}
        
        logger.debug(f"Fetching tool definitions for bot {self._bot_id}")
        try:
            response = await self._client.get(url, params=params, timeout=15.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to get tool definitions, status {e.response.status_code}: {e.response.text}")
            return []
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"An error occurred while requesting tool definitions: {e}")
            return []
        except Exception as e:
            logger.error(f"An unexpected error occurred in get_tool_definitions: {e}", exc_info=True)
            return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Requests the backend to execute a specific tool with the given arguments.
        """
        url = f"{self._base_url}/api/tools/call"
        payload = {
            "bot_id": self._bot_id,
            "tool_name": tool_name,
            "arguments": arguments
        }
        
        logger.info(f"Requesting execution of tool '{tool_name}' with args: {arguments}")
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            # Handle cases where the response body is empty but status is OK
            if not response.content:
                return {"jsonrpc": "2.0", "error": {"code": -32003, "message": "API returned an empty successful response."}}
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Tool call failed with status {e.response.status_code}: {e.response.text}")
            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": f"API Error: {e.response.text}"}}
        except httpx.RequestError as e:
            logger.error(f"An error occurred while calling tool '{tool_name}': {e}")
            return {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Network error while contacting tool proxy."}}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON from tool call response: {e.doc}")
            return {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Invalid JSON response from the server."}}
        except Exception as e:
            logger.error(f"An unexpected error occurred in call_tool: {e}", exc_info=True)
            return {"jsonrpc": "2.0", "error": {"code": -32002, "message": "An unexpected client error occurred."}}

    async def process_message(
        self,
        user_id: str,
        user_display_name: str,
        channel_id: str,
        message_id: str,
        message_content: str,
        history: List[Dict[str, Any]],
        is_direct_message: bool,
        is_direct_mention: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Sends a message and its context to the backend's main processing endpoint.
        """
        url = f"{self._base_url}/api/chat/process_message"
        payload = {
            "bot_id": self._bot_id,
            "user_id": user_id,
            "user_display_name": user_display_name,
            "channel_id": channel_id,
            "message_id": message_id,
            "message_content": message_content,
            "history": history,
            "is_direct_message": is_direct_message,
            "is_direct_mention": is_direct_mention
        }
        
        logger.debug(f"Calling process_message API for message_id: {message_id}")
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"API request failed with status {e.response.status_code}: {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"An error occurred while requesting {e.request.url!r}: {e}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred in APIClient.process_message: {e}", exc_info=True)
            return None

    async def stream_final_response(self, stream_url: str) -> AsyncGenerator[str, None]:
        """
        Connects to a Server-Sent Events (SSE) stream and yields the content of each event.
        """
        url = f"{self._base_url}{stream_url}"
        logger.info(f"Connecting to SSE stream at {url}")
        try:
            async with self._client.stream("GET", url) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        try:
                            data_str = line[len("data:"):].strip()
                            if data_str:
                                data = json.loads(data_str)
                                if "content" in data:
                                    yield data["content"]
                                elif "error" in data:
                                    logger.error(f"Received error from stream: {data['error']}")
                                    yield f"\n\n_Sorry, an error occurred while generating the response: {data['error']}_"
                                    break
                        except json.JSONDecodeError:
                            logger.warning(f"Could not decode JSON from stream line: {line}")
                            continue
        except httpx.HTTPStatusError as e:
            error_msg = f"Streaming connection failed with status {e.response.status_code}: {e.response.text}"
            logger.error(error_msg)
            yield f"\n\n_Sorry, I couldn't retrieve the final response. {error_msg}_"
        except Exception as e:
            logger.error(f"An unexpected error occurred during streaming: {e}", exc_info=True)
            yield "\n\n_Sorry, a critical error occurred while retrieving the final response._"

    async def archive_conversation(
        self,
        user_id: str,
        user_display_name: str,
        user_name: str,
        conversation_history: List[Dict[str, Any]]
    ):
        """
        Sends a completed conversation to the backend for archival.
        """
        url = f"{self._base_url}/api/archive"
        payload = {
            "bot_id": self._bot_id,
            "user_id": user_id,
            "user_display_name": user_display_name,
            "user_name": user_name,
            "conversation_history": conversation_history
        }

        logger.debug(f"Calling archive API for user {user_display_name}")
        try:
            short_timeout_client = httpx.AsyncClient(timeout=10.0)
            await short_timeout_client.post(url, json=payload)
            await short_timeout_client.aclose()
        except Exception as e:
            logger.error(f"An error occurred during conversation archiving: {e}", exc_info=True)