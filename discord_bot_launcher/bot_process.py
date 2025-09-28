import argparse
import asyncio
import logging
import sys

import discord
from discord.ext import commands

# We import the event handler from our new modular structure
from client import event_handler
from client.api_client import APIClient

# --- Logging Setup ---
# Using sys.stdout to ensure logs are captured by Docker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """
    Main function to configure and run the Discord bot process.
    """
    # --- Argument Parsing ---
    # This allows launcher.py to pass bot-specific info to this process
    parser = argparse.ArgumentParser(description="GroBot Discord Bot Process")
    parser.add_argument("--token", required=True, help="Discord Bot Token")
    parser.add_argument("--bot-id", required=True, type=int, help="Bot ID from the database")
    parser.add_argument("--api-base-url", required=True, help="Base URL for the GroBot API")
    args = parser.parse_args()

    # --- Bot Initialization ---
    # Define the intents required for the bot to function
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    # The bot instance is created with a command prefix, though we primarily use on_message
    bot = commands.Bot(command_prefix="!", intents=intents)

    # --- API Client Setup ---
    # Create a single, reusable instance of our API client
    api_client = APIClient(base_url=args.api_base_url, bot_id=args.bot_id)

    # --- Event Handler Attachment ---
    # This is the core of the refactoring: we attach the handler from our separate module.
    # We pass the bot instance and the api_client to the handler's setup function.
    await event_handler.setup(bot, api_client)
    
    # --- Bot Startup ---
    logger.info(f"Bot process for bot_id {args.bot_id} starting...")
    try:
        await bot.start(args.token)
    except discord.LoginFailure:
        logger.critical("Failed to log in to Discord. Please check the provided token.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during bot startup: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())