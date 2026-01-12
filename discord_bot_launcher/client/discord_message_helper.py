"""
Discord Message Helper
=====================

This module provides helper functions for sending formatted messages to Discord,
with special handling for long text blocks, code formatting, and file attachments.

History & Design Decisions:
---------------------------
1. Created to centralize Discord message formatting logic that was previously
   scattered across event_handler.py and discord_ui.py
2. Designed to handle Discord's 2000-character limit intelligently by:
   - Splitting long messages into multiple parts when possible
   - Converting to file attachments when splitting isn't feasible
   - Preserving code formatting with proper syntax highlighting
3. Uses async/await patterns consistent with discord.py library
4. Provides both high-level convenience functions and low-level utilities

Key Features:
-------------
- send_code_block(): Send code with syntax highlighting
- send_long_text(): Send long text with smart splitting
- format_code_block(): Utility to format text as code block
- split_message_by_lines(): Intelligent message splitting
"""

import io
import logging
from typing import Optional, List, Tuple
import discord

logger = logging.getLogger(__name__)

# Discord limits
DISCORD_CHAR_LIMIT = 2000
DISCORD_FILE_SIZE_LIMIT = 8 * 1024 * 1024  # 8 MB for most servers

# Code block formatting
CODE_BLOCK_PREFIX = "```"
CODE_BLOCK_SUFFIX = "```"


def format_code_block(content: str, language: str = "") -> str:
    """
    Format text as a Discord code block with optional language syntax highlighting.
    
    Args:
        content: The text content to format
        language: Programming language for syntax highlighting (e.g., 'python', 'json', 'yaml')
    
    Returns:
        Formatted code block string
    
    Example:
        >>> format_code_block("print('hello')", "python")
        "```python\nprint('hello')\n```"
    """
    if language:
        return f"{CODE_BLOCK_PREFIX}{language}\n{content}\n{CODE_BLOCK_SUFFIX}"
    return f"{CODE_BLOCK_PREFIX}\n{content}\n{CODE_BLOCK_SUFFIX}"


def split_message_by_lines(text: str, max_length: int = DISCORD_CHAR_LIMIT) -> List[str]:
    """
    Split a long text into multiple parts, trying to break at line boundaries.
    
    Args:
        text: The text to split
        max_length: Maximum length for each part
    
    Returns:
        List of text parts, each within max_length
    
    Note:
        Tries to split at newlines first, falls back to character splitting
        if a single line exceeds max_length
    """
    if len(text) <= max_length:
        return [text]
    
    parts = []
    lines = text.split('\n')
    current_part = ""
    
    for line in lines:
        # If adding this line would exceed limit, save current part and start new
        if len(current_part) + len(line) + 1 > max_length:
            if current_part:
                parts.append(current_part.rstrip('\n'))
                current_part = ""
            
            # If a single line is too long, split it by characters
            if len(line) > max_length:
                while len(line) > max_length:
                    parts.append(line[:max_length])
                    line = line[max_length:]
                current_part = line + '\n' if line else ''
            else:
                current_part = line + '\n'
        else:
            current_part += line + '\n'
    
    if current_part:
        parts.append(current_part.rstrip('\n'))
    
    return parts


async def send_code_block(
    channel_or_interaction,
    code: str,
    language: str = "",
    header: str = "",
    filename: str = "code.txt"
) -> List[discord.Message]:
    """
    Send code to Discord as a formatted code block, handling length limits.
    
    Args:
        channel_or_interaction: Discord TextChannel or Interaction object
        code: The code content to send
        language: Syntax highlighting language (e.g., 'python', 'json')
        header: Optional header text to include before the code block
        filename: Filename to use if sending as file attachment
    
    Returns:
        List of sent message objects
    
    Behavior:
        1. Formats code with language-specific syntax highlighting
        2. If total message ≤ 2000 chars: sends as regular message
        3. If > 2000 chars: sends as file attachment (preserves integrity for copy/paste)
    """
    formatted_code = format_code_block(code, language)
    full_message = f"{header}\n{formatted_code}" if header else formatted_code
    
    # If within limits, send directly as code block
    if len(full_message) <= DISCORD_CHAR_LIMIT:
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(full_message)
            return [message]
        else:  # Interaction
            await channel_or_interaction.followup.send(full_message)
            # Can't return message from followup.send without await
            return []
    
    # If exceeds limit, send as file attachment to preserve integrity
    logger.info(f"Code block exceeds Discord limit, sending as file: {filename}")
    try:
        buffer = io.StringIO(code)
        buffer.seek(0)
        code_file = discord.File(buffer, filename=filename)
        
        file_message = header if header else "Here is the code (sent as file to preserve formatting):"
        
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(content=file_message, file=code_file)
            return [message]
        else:
            await channel_or_interaction.followup.send(content=file_message, file=code_file)
            return []
            
    except Exception as e:
        logger.error(f"Failed to send code as file: {e}", exc_info=True)
        error_msg = f"{header}\n_This code block was too long and an error occurred while sending it as a file._"
        
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(error_msg)
            return [message]
        else:
            await channel_or_interaction.followup.send(error_msg)
            return []


async def send_long_text(
    channel_or_interaction,
    text: str,
    header: str = "",
    filename: str = "text.txt",
    as_code_block: bool = False,
    language: str = ""
) -> List[discord.Message]:
    """
    Send long text to Discord, handling length limits.
    
    Args:
        channel_or_interaction: Discord TextChannel or Interaction object
        text: The text content to send
        header: Optional header text
        filename: Filename to use if sending as file attachment
        as_code_block: Whether to format as code block
        language: Language for syntax highlighting if as_code_block is True
    
    Returns:
        List of sent message objects
    
    Behavior:
        - For code blocks: sends as file if exceeds Discord limit (preserves integrity)
        - For plain text: splits into multiple messages for readability
    """
    if as_code_block:
        return await send_code_block(channel_or_interaction, text, language, header, filename)
    
    # For plain text, we can split for better readability
    full_message = f"{header}\n{text}" if header else text
    
    if len(full_message) <= DISCORD_CHAR_LIMIT:
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(full_message)
            return [message]
        else:
            await channel_or_interaction.followup.send(full_message)
            return []
    
    # Split the text for plain text (not code blocks)
    text_parts = split_message_by_lines(text, DISCORD_CHAR_LIMIT - 50)  # Reserve space for headers
    
    # If reasonable number of parts, send as multiple messages
    if len(text_parts) <= 5:
        messages = []
        for i, part in enumerate(text_parts):
            part_header = f"{header} (Part {i+1}/{len(text_parts)})" if header else f"(Part {i+1}/{len(text_parts)})"
            part_message = f"{part_header}\n{part}"
            
            if isinstance(channel_or_interaction, discord.TextChannel):
                message = await channel_or_interaction.send(part_message)
                messages.append(message)
            else:
                await channel_or_interaction.followup.send(part_message)
        
        return messages
    
    # Too many parts, send as file
    logger.info(f"Text has too many parts ({len(text_parts)}), sending as file: {filename}")
    try:
        buffer = io.StringIO(text)
        buffer.seek(0)
        text_file = discord.File(buffer, filename=filename)
        
        file_message = header if header else "Here is the text:"
        
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(content=file_message, file=text_file)
            return [message]
        else:
            await channel_or_interaction.followup.send(content=file_message, file=text_file)
            return []
            
    except Exception as e:
        logger.error(f"Failed to send text as file: {e}", exc_info=True)
        error_msg = f"{header}\n_This text was too long and an error occurred while sending it as a file._"
        
        if isinstance(channel_or_interaction, discord.TextChannel):
            message = await channel_or_interaction.send(error_msg)
            return [message]
        else:
            await channel_or_interaction.followup.send(error_msg)
            return []


# Backward compatibility wrapper
async def send_prompt_part(
    interaction: discord.Interaction,
    header: str,
    prompt_content: str,
    filename: str = "prompt.txt"
) -> List[discord.Message]:
    """
    Backward compatibility wrapper for the original _send_prompt_part function.
    
    Args:
        interaction: Discord Interaction object
        header: Header text
        prompt_content: Prompt content
        filename: Filename for attachment
    
    Returns:
        List of sent message objects (empty list for Interaction followup)
    """
    return await send_long_text(
        interaction,
        prompt_content,
        header=header,
        filename=filename,
        as_code_block=True,
        language=""
    )