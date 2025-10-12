####
# FICHIER: app/core/websocket_manager.py
####
import asyncio
import json
import uuid
import logging
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Any

# Get the logger for this module
logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages active WebSocket connections from bot processes.
    """
    def __init__(self):
        # Maps bot_id to its active WebSocket connection
        self.active_connections: Dict[int, WebSocket] = {}
        # Stores future objects for request-response calls
        self.pending_requests: Dict[str, asyncio.Future] = {}

    async def connect(self, bot_id: int, websocket: WebSocket):
        """
        Accepts and registers a new WebSocket connection for a bot.
        """
        await websocket.accept()
        self.active_connections[bot_id] = websocket
        logger.info(f"WebSocket connection established for bot_id: {bot_id}")

    def disconnect(self, bot_id: int):
        """
        Removes a bot's WebSocket connection from the registry.
        """
        if bot_id in self.active_connections:
            del self.active_connections[bot_id]
            logger.info(f"WebSocket connection closed for bot_id: {bot_id}")

    async def send_to_bot(self, bot_id: int, message: Dict[str, Any]):
        """
        Sends a JSON message to a specific bot (fire and forget).
        """
        if bot_id in self.active_connections:
            websocket = self.active_connections[bot_id]
            logger.info(f"Attempting to send message to bot {bot_id}: {json.dumps(message)}")
            try:
                await websocket.send_json(message)
                logger.info(f"Message successfully sent to bot {bot_id}.")
            except WebSocketDisconnect:
                logger.warning(f"Bot {bot_id} disconnected during send. Cleaning up stale connection.")
                self.disconnect(bot_id)
                raise ValueError(f"Bot {bot_id} disconnected.")
            except Exception as e:
                logger.error(f"An unexpected error occurred while sending to bot {bot_id}: {e}", exc_info=True)
                raise
        else:
            logger.error(f"Attempted to send message to bot {bot_id}, but it is not connected.")
            raise ValueError(f"Bot {bot_id} is not connected.")

    async def request(self, bot_id: int, message: Dict[str, Any], timeout: int = 10) -> Any:
        """
        Sends a request to a bot and waits for a response.
        """
        if bot_id not in self.active_connections:
            raise ValueError(f"Bot {bot_id} is not connected.")

        request_id = str(uuid.uuid4())
        message["request_id"] = request_id

        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_id] = future

        try:
            await self.send_to_bot(bot_id, message)
            # Wait for the future to be resolved with a timeout
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # Clean up the pending request if it times out
            del self.pending_requests[request_id]
            raise TimeoutError(f"Request {request_id} to bot {bot_id} timed out.")
        finally:
            # Ensure cleanup even if another exception occurs
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
    
    def resolve_request(self, request_id: str, response_data: Any):
        """
        Called by the main WebSocket handler to resolve a pending future.
        """
        if request_id in self.pending_requests:
            future = self.pending_requests[request_id]
            if not future.done():
                future.set_result(response_data)


# Create a single instance to be used throughout the application
websocket_manager = ConnectionManager()