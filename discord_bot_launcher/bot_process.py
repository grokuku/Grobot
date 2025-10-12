#// FICHIER: discord_bot_launcher/bot_process.py

import argparse
import asyncio
import logging
import sys
import json
import io
import websockets
import httpx
from PIL import Image
from urllib.parse import urlparse
from os.path import basename, splitext

import discord
from discord.ext import commands

from client import event_handler
from client.api_client import APIClient

# --- Constants ---
DISCORD_FILE_SIZE_LIMIT = 8 * 1024 * 1024  # 8 MB
DISCORD_MESSAGE_LIMIT = 2000

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# --- WebSocket Communication Handler ---
async def websocket_listener(bot: commands.Bot, bot_id: int, ws_url: str):
    """
    Connects to the backend WebSocket and handles incoming commands.
    """
    while True:
        try:
            async with websockets.connect(ws_url) as websocket:
                logger.info(f"WebSocket connected for bot {bot_id} to {ws_url}")
                while True:
                    message_str = await websocket.recv()
                    message = json.loads(message_str)
                    logger.info(f"Received command via WebSocket: {message.get('action')}")
                    
                    action = message.get("action")
                    if action == "get_channels":
                        await handle_get_channels(bot, websocket, message)
                    elif action == "post_to_channel":
                        await handle_post_to_channel(bot, message)
                    else:
                        logger.warning(f"Unknown WebSocket action: {action}")
        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            logger.warning(f"WebSocket connection lost: {e}. Retrying in 15 seconds...")
            await asyncio.sleep(15)
        except Exception as e:
            logger.error(f"An error occurred in the WebSocket listener: {e}", exc_info=True)
            await asyncio.sleep(15)


async def handle_get_channels(bot: commands.Bot, websocket, request_message: dict):
    """
    Gathers all text channels and sends them back through the WebSocket.
    """
    channels = []
    for guild in bot.guilds:
        for channel in guild.text_channels:
            channels.append({"id": str(channel.id), "name": f"{guild.name} - #{channel.name}"})
    
    response = {
        "request_id": request_message.get("request_id"),
        "response": channels
    }
    await websocket.send(json.dumps(response))
    logger.info("Sent channel list to backend.")


async def handle_post_to_channel(bot: commands.Bot, message: dict):
    """
    Processes and posts a message with up to 10 attachments to a Discord channel.
    """
    # --- LOGGING ADDED ---
    logger.info(f"Handling 'post_to_channel'. Full received message: {json.dumps(message, indent=2)}")
    # --- END LOGGING ---

    payload = message.get("payload", {})
    channel_id = payload.get("channel_id")
    message_content = payload.get("message_content")
    attachments = payload.get("attachments", [])

    if not channel_id:
        logger.error("No channel_id provided in post_to_channel payload.")
        return

    channel = bot.get_channel(int(channel_id))
    if not channel:
        logger.error(f"Could not find channel with ID: {channel_id}")
        return
    
    discord_files = []
    if attachments:
        tasks = [process_attachment(att) for att in attachments]
        results = await asyncio.gather(*tasks)
        discord_files = [res for res in results if res is not None]

    try:
        await channel.send(content=message_content, files=discord_files or None)
        logger.info(f"Successfully posted content to channel {channel_id}.")
    except Exception as e:
        logger.error(f"Failed to send message to channel {channel_id}: {e}", exc_info=True)


async def process_attachment(attachment: dict) -> discord.File | None:
    """
    Processes a single attachment dictionary (from data URL or text) into a discord.File object.
    Handles image compression and text-to-file conversion. Auto-detects filename from URL if not provided.
    """
    attachment_data = attachment.get("data")
    filename = attachment.get("filename")

    if not attachment_data:
        return None

    # Case 1: Attachment data is a URL
    if attachment_data.startswith("http"):
        # Auto-detect filename if not provided
        if not filename:
            try:
                parsed_url = urlparse(attachment_data)
                filename = basename(parsed_url.path)
                if not filename: raise ValueError("Path is empty")
                logger.info(f"Auto-detected filename from URL: {filename}")
            except Exception as e:
                logger.warning(f"Could not auto-detect filename from URL {attachment_data}: {e}. Falling back.")
                filename = 'downloaded_file'
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(attachment_data, follow_redirects=True)
                response.raise_for_status()
            
            content_bytes = response.content
            content_type = response.headers.get("content-type", "")
            final_filename = filename
            
            # If it's an image and it's too large, compress it
            if content_type.startswith("image/") and len(content_bytes) > DISCORD_FILE_SIZE_LIMIT:
                logger.info(f"Image '{filename}' exceeds size limit, attempting compression...")
                original_file = io.BytesIO(content_bytes)
                img = Image.open(original_file)
                
                compressed_file = io.BytesIO()
                # Convert to RGB to ensure JPEG compatibility
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(compressed_file, format='JPEG', quality=85, optimize=True)
                
                if len(compressed_file.getvalue()) > DISCORD_FILE_SIZE_LIMIT:
                    logger.warning(f"Image '{filename}' is still too large after compression.")
                    return None
                
                content_bytes = compressed_file.getvalue()
                # Change extension to .jpg after compression
                base_name = splitext(filename)[0]
                final_filename = f"{base_name}.jpg"

            return discord.File(io.BytesIO(content_bytes), filename=final_filename)
        except Exception as e:
            logger.error(f"Failed to process URL attachment {attachment_data}: {e}", exc_info=True)
            return None

    # Case 2: Attachment data is raw text, convert to file if it's long
    elif isinstance(attachment_data, str) and len(attachment_data.encode('utf-8')) > DISCORD_MESSAGE_LIMIT - 10:
        text_bytes = attachment_data.encode('utf-8')
        return discord.File(io.BytesIO(text_bytes), filename=filename or 'result.txt')
    
    # If text is short, it should be handled in message_content, not as a file.
    # This also covers cases of non-string, non-http data.
    return None

async def main():
    """
    Main function to configure and run the Discord bot process.
    """
    parser = argparse.ArgumentParser(description="GroBot Discord Bot Process")
    parser.add_argument("--token", required=True, help="Discord Bot Token")
    parser.add_argument("--bot-id", required=True, type=int, help="Bot ID from the database")
    parser.add_argument("--api-base-url", required=True, help="Base URL for the GroBot API")
    args = parser.parse_args()

    ws_url = args.api_base_url.replace("http", "ws", 1) + f"/ws/bots/{args.bot_id}"

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    api_client = APIClient(base_url=args.api_base_url, bot_id=args.bot_id)

    await event_handler.setup(bot, api_client)
    
    # Use setup_hook to start background tasks like our WebSocket listener
    @bot.event
    async def on_ready():
        logger.info(f'Bot {bot.user} is ready and connected to Discord.')
    
    # The setup_hook is a reliable place to start tasks that run for the bot's lifetime
    async def setup_hook():
        bot.loop.create_task(websocket_listener(bot, args.bot_id, ws_url))
    
    bot.setup_hook = setup_hook

    logger.info(f"Bot process for bot_id {args.bot_id} starting...")
    try:
        await bot.start(args.token)
    except discord.LoginFailure:
        logger.critical("Failed to log in to Discord. Please check the provided token.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during bot startup: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())