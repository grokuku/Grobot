#### Fichier : discord_bot_launcher/client/discord_ui.py
import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)

# --- Constants for Reactions ---
REACTION_THINKING = '🤔'
REACTION_WORKING = '💬'


async def add_thinking_reaction(message: discord.Message):
    """Adds the initial 'thinking' reaction to a user's message."""
    try:
        await message.add_reaction(REACTION_THINKING)
    except discord.Forbidden:
        logger.warning(f"Missing permissions to add reactions in channel {message.channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Failed to add 'thinking' reaction: {e}", exc_info=True)


async def update_reaction_to_working(message: discord.Message):
    """Removes the 'thinking' reaction and adds the 'working' reaction."""
    try:
        await remove_bot_reactions(message)
        await message.add_reaction(REACTION_WORKING)
    except discord.Forbidden:
            logger.warning(f"Missing permissions to manage reactions in channel {message.channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Failed to update reaction to 'working': {e}", exc_info=True)


async def remove_bot_reactions(message: discord.Message):
    """Removes all reactions added by the bot itself from a message."""
    if not message.guild or not message.guild.me:
        return

    try:
        for reaction in message.reactions:
            async for user in reaction.users():
                if user.id == message.guild.me.id:
                    await reaction.remove(message.guild.me)
                    break
    except discord.Forbidden:
        logger.warning(f"Missing permissions to remove reactions in channel {message.channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Failed to remove bot reactions: {e}", exc_info=True)


async def send_message(channel: discord.TextChannel, content: str) -> Optional[discord.Message]:
    """Sends a simple text message to a channel and returns the message object."""
    if not content:
        logger.warning("Attempted to send an empty message.")
        return None

    try:
        return await channel.send(content)
    except discord.Forbidden:
        logger.error(f"Missing permissions to send messages in channel {channel.id}")
        return None
    except discord.HTTPException as e:
        logger.error(f"Failed to send message to channel {channel.id}: {e}", exc_info=True)
        return None


# --- MODIFIED FUNCTION ---
async def edit_message(message: discord.Message, **kwargs):
    """
    Edits an existing message. This is a robust wrapper around discord.py's message.edit()
    to provide centralized logging and accept any valid keyword argument (e.g., content, attachments, view).
    """
    # Add a placeholder for empty content to prevent Discord API errors
    if 'content' in kwargs and not kwargs['content']:
        kwargs['content'] = "..."

    try:
        await message.edit(**kwargs)
    except discord.Forbidden:
        logger.error(f"Missing permissions to edit message {message.id} in channel {message.channel.id}")
    except discord.HTTPException as e:
        logger.error(f"Failed to edit message {message.id}: {e}", exc_info=True)