import logging
import asyncio
import time
import json
import re
import io
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, Select, View, Button
import httpx
import websockets
from PIL import Image

from . import discord_ui as ui
from .api_client import APIClient

logger = logging.getLogger(__name__)
_bot_instance: Optional[commands.Bot] = None
_api_client_instance: Optional[APIClient] = None

async def _replace_mentions(content: str, message: discord.Message) -> str:
    if not content:
        return ""
    user_ids = re.findall(r'<@!?(\d+)>', content)
    for user_id in user_ids:
        user = None
        if message.guild:
            user = message.guild.get_member(int(user_id))
        if not user:
            user = _bot_instance.get_user(int(user_id))
        
        if user:
            content = re.sub(f'<@!?{user_id}>', f'@{user.display_name}', content)
    return content

async def _fetch_history(message: discord.Message, limit: int = 10) -> List[Dict[str, Any]]:
    history = []
    if hasattr(message.channel, 'history'):
        async for msg in message.channel.history(limit=limit, before=message):
            if not msg.content: continue
            role = "assistant" if msg.author.id == _bot_instance.user.id else "user"
            clean_content = await _replace_mentions(msg.content, msg)
            history.append({"role": role, "content": clean_content})
    history.reverse()
    return history

async def _handle_streaming_response(channel: discord.TextChannel, stream_url: str):
    UPDATE_INTERVAL_SECONDS = 1.5
    UPDATE_BUFFER_SIZE_CHARS = 100
    response_message = await ui.send_message(channel, "...")
    if not response_message:
        logger.error("Failed to send initial message for streaming response.")
        return
    full_content = ""
    update_buffer = ""
    last_update_time = time.time()
    try:
        async for chunk in _api_client_instance.stream_final_response(stream_url):
            if not chunk: continue
            full_content += chunk
            update_buffer += chunk
            current_time = time.time()
            if (current_time - last_update_time >= UPDATE_INTERVAL_SECONDS) or (len(update_buffer) >= UPDATE_BUFFER_SIZE_CHARS):
                if full_content.strip():
                    await ui.edit_message(response_message, content=full_content)
                update_buffer = ""
                last_update_time = current_time
    finally:
        if response_message.content != full_content:
            await ui.edit_message(response_message, content=full_content or "...")

async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.type == discord.MessageType.chat_input_command: return

    await ui.add_thinking_reaction(message)
    
    try:
        is_dm = isinstance(message.channel, discord.DMChannel)
        
        is_direct_mention = (
            is_dm or
            f'<@{_bot_instance.user.id}>' in message.content or
            (message.reference and isinstance(message.reference.resolved, discord.Message) and message.reference.resolved.author.id == _bot_instance.user.id)
        )
        is_direct_mention = bool(is_direct_mention)

        clean_current_content = await _replace_mentions(message.content, message)

        history = await _fetch_history(message)
        history.append({"role": "user", "content": clean_current_content})
        
        response = await _api_client_instance.process_message(
            user_id=str(message.author.id),
            user_display_name=message.author.display_name,
            channel_id=str(message.channel.id),
            message_id=str(message.id),
            message_content=clean_current_content,
            history=history,
            is_direct_message=is_dm,
            is_direct_mention=is_direct_mention
        )

        if not response:
            await ui.send_message(message.channel, "Sorry, I encountered an error while processing your request.")
            return

        action = response.get("action")
        logger.info(f"Received action '{action}' from orchestrator for message {message.id}")
        
        if action == "STOP":
            logger.info(f"Orchestrator decided to stop. Reason: {response.get('reason')}")
            return

        if action in ["CLARIFY", "ACKNOWLEDGE_AND_EXECUTE", "SYNTHESIZE"]:
            await ui.update_reaction_to_working(message)

        if action == "CLARIFY":
            await ui.send_message(message.channel, response.get("message"))
        elif action == "ACKNOWLEDGE_AND_EXECUTE":
            await ui.send_message(message.channel, response.get("acknowledgement_message"))
            asyncio.create_task(_handle_streaming_response(
                message.channel, response.get("final_response_stream_url")
            ))
        elif action == "SYNTHESIZE":
            asyncio.create_task(_handle_streaming_response(
                message.channel, response.get("final_response_stream_url")
            ))
        else:
            logger.error(f"Received an unknown action from the orchestrator: '{action}'")
            await ui.send_message(message.channel, "Sorry, I received an unknown instruction from my brain.")

    except Exception as e:
        logger.critical(f"A critical error occurred in the on_message handler: {e}", exc_info=True)
        try:
            await ui.send_message(message.channel, "I'm sorry, a critical internal error occurred.")
        except Exception: pass
    finally:
        await ui.remove_bot_reactions(message)

TOOL_SCHEMA_CACHE: Dict[str, Any] = {}
TOOL_SCHEMA_CACHE_EXPIRY = timedelta(minutes=5)
async def _get_tool_definitions_with_cache() -> List[Dict]:
    global TOOL_SCHEMA_CACHE
    now = datetime.now(timezone.utc)
    if 'data' in TOOL_SCHEMA_CACHE and (now - TOOL_SCHEMA_CACHE.get('timestamp', datetime.min.replace(tzinfo=timezone.utc))) < TOOL_SCHEMA_CACHE_EXPIRY:
        return TOOL_SCHEMA_CACHE['data']
    definitions = await _api_client_instance.get_tool_definitions()
    if definitions:
        TOOL_SCHEMA_CACHE = {'data': definitions, 'timestamp': now}
    return definitions
async def _get_choices_for_tool_param(tool_name: str, param_name: str, current_input: str) -> List[app_commands.Choice[str]]:
    definitions = await _get_tool_definitions_with_cache()
    tool_def = next((t for t in definitions if t.get("name") == tool_name), None)
    if not tool_def or not (schema := tool_def.get("inputSchema", {}).get("properties", {}).get(param_name)): return []
    available_choices = schema.get("enum", [])
    if not available_choices: return []
    last_part = current_input.split(',')[-1].strip().lower()
    filtered_choices = [choice for choice in available_choices if last_part in choice.lower()]
    return [app_commands.Choice(name=choice, value=choice) for choice in filtered_choices[:25]]
def _find_image_url_in_message(message: discord.Message) -> Optional[str]:
    for attachment in message.attachments:
        if attachment.content_type and attachment.content_type.startswith("image/"): return attachment.url
    for embed in message.embeds:
        if embed.image and embed.image.url: return embed.image.url
        if embed.thumbnail and embed.thumbnail.url: return embed.thumbnail.url
    if url_match := re.search(r'https?://\S+\.(?:png|jpg|jpeg|webp|gif)', message.content, re.IGNORECASE):
        return url_match.group(0)
    return None
async def _download_and_prepare_file(image_url: str, guild: Optional[discord.Guild]) -> Tuple[Optional[discord.File], Optional[str]]:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(image_url)
            response.raise_for_status()
            image_bytes = response.content
            filename = image_url.split('/')[-1]
        SAFE_COMPRESSION_THRESHOLD = 7.5 * 1024 * 1024
        if len(image_bytes) > SAFE_COMPRESSION_THRESHOLD:
            logger.info(f"Image size ({len(image_bytes)}) exceeds threshold. Attempting compression.")
            try:
                with Image.open(io.BytesIO(image_bytes)) as img:
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    compressed_buffer = io.BytesIO()
                    img.save(compressed_buffer, format='JPEG', quality=95, optimize=True)
                    if compressed_buffer.tell() < (guild.filesize_limit if guild else 8 * 1024 * 1024):
                        image_bytes = compressed_buffer.getvalue()
                        filename = (filename.rsplit('.', 1)[0] if '.' in filename else filename) + ".jpg"
                    else:
                        logger.warning("Image compression failed to reduce size sufficiently.")
            except Exception as e:
                logger.error(f"Error during image compression: {e}")
        return discord.File(io.BytesIO(image_bytes), filename=filename), None
    except Exception as e:
        error_msg = f"Failed to retrieve or process the image from {image_url}."
        return None, error_msg
        
# --- START OF FIX ---
async def _handle_mcp_stream(websocket_url: str) -> Dict:
    try:
        async with websockets.connect(websocket_url) as websocket:
            async for message_str in websocket:
                message_data = json.loads(message_str)
                params = message_data.get("params", {})
                if message_data.get("method") in ("stream/chunk", "stream/end"):
                    if error_obj := params.get("error"): return {"error": {"message": error_obj.get("message", "Unknown error")}}
                    elif result_obj := params.get("result"): return {"result": result_obj}
    except Exception as e:
        logger.error(f"MCP stream connection error at {websocket_url}: {e}")
        return {"error": {"message": f"Failed to handle the tool stream: {e}"}}
    return {"error": {"message": "Tool stream ended without a result."}}
# --- END OF FIX ---

async def _execute_and_process_tool_call(interaction: discord.Interaction, tool_name: str, arguments: Dict[str, Any]):
    acknowledgement_message: Optional[discord.Message] = None
    try:
        all_tools = await _get_tool_definitions_with_cache()
        tool_def = next((t for t in all_tools if t.get("name") == tool_name), None)
        if not tool_def:
            await interaction.response.send_message(f"Sorry, I couldn't find the tool named `{tool_name}`.", ephemeral=True)
            return

        is_slow = tool_def.get("is_slow", False)
        reaction_emoji = tool_def.get("reaction_emoji")

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        
        if is_slow:
            ack_content = f"Understood, I'm generating it now!"
            acknowledgement_message = await interaction.followup.send(ack_content, wait=True)
            if reaction_emoji:
                await acknowledgement_message.add_reaction(reaction_emoji)

        result = await _api_client_instance.call_tool(tool_name, arguments)
        if not result: raise Exception("Tool call failed: No response from backend.")
        if result.get("method") == "stream/start" and (ws_url := result.get("params", {}).get("ws_url")):
            result = await _handle_mcp_stream(ws_url)
        if "error" in result:
            error_message = result.get("error", {}).get("message", "An unknown error occurred.")
            raise Exception(f"Tool execution failed: {error_message}")

        content_list = result.get("result", {}).get("content", [])
        text_parts = [f"<@{interaction.user.id}>, here is the image you requested!"]
        files_to_send = []
        
        for block in content_list:
            if block.get("type") == "text": 
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "image" and (url := block.get("source")):
                image_file, error_msg = await _download_and_prepare_file(url, interaction.guild)
                if image_file: 
                    files_to_send.append(image_file)
                if error_msg: 
                    text_parts.append(f"_{error_msg}_") # Italicize image download errors
        
        # Append the formatted prompt used, if available
        if tool_name == "generate_image" and "prompt" in arguments:
            text_parts.append(f"Prompt used: `{arguments['prompt']}`")
        
        final_text = "\n".join(text_parts).strip()

        # Send the final result as a new message
        await interaction.followup.send(content=final_text, files=files_to_send)

        # Clean up the acknowledgement message if one was sent
        if acknowledgement_message:
            try:
                await acknowledgement_message.delete()
            except discord.HTTPException as e:
                logger.warning(f"Could not delete acknowledgement message {acknowledgement_message.id}: {e}")

    except Exception as e:
        logger.critical(f"Critical error in tool execution flow for '{tool_name}': {e}", exc_info=True)
        error_message = f"Sorry, a critical internal error occurred: {e}"
        # Use followup.send for errors to ensure a message is always sent
        await interaction.followup.send(error_message, ephemeral=True)
    finally:
        pass

class UpscaleOptionsModal(Modal, title='Advanced Upscale Options'):
    def __init__(self, target_message: discord.Message, image_url: str, upscale_type: Optional[str]):
        super().__init__()
        self.target_message = target_message
        self.image_url = image_url
        self.upscale_type = upscale_type
    prompt = TextInput(label="Prompt (Optional)", style=discord.TextStyle.paragraph, required=False)
    denoise = TextInput(label="Denoise (Optional, e.g., 0.5)", required=False)
    seed = TextInput(label="Seed (Optional, e.g., 12345 or -1)", required=False)
    async def on_submit(self, interaction: discord.Interaction):
        args = {"input_image_url": self.image_url, "upscale_type": self.upscale_type, "prompt": self.prompt.value, "denoise": self.denoise.value, "seed": self.seed.value}
        args = {k: v for k, v in args.items() if v}
        await _execute_and_process_tool_call(interaction, "upscale_image", args)

class UpscaleControlView(View):
    def __init__(self, original_interaction: discord.Interaction, target_message: discord.Message, image_url: str, choices: List[str]):
        super().__init__(timeout=300)
        self.original_interaction = original_interaction
        self.target_message = target_message
        self.image_url = image_url
        self.selected_type: Optional[str] = None
        if choices:
            self.type_select = Select(placeholder="Choose an upscale type...", options=[discord.SelectOption(label=c) for c in choices[:25]])
            self.type_select.callback = self.select_callback
            self.add_item(self.type_select)
    async def select_callback(self, interaction: discord.Interaction):
        self.selected_type = self.type_select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label="Start Upscale", style=discord.ButtonStyle.success)
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if not self.selected_type:
            await interaction.response.send_message("Please select an upscale type first.", ephemeral=True)
            return
        await interaction.response.edit_message(content=f"Starting upscale (`{self.selected_type}`)...", view=None)
        await _execute_and_process_tool_call(interaction, "upscale_image", {"input_image_url": self.image_url, "upscale_type": self.selected_type})
    @discord.ui.button(label="Advanced...", style=discord.ButtonStyle.secondary)
    async def advanced_button(self, interaction: discord.Interaction, button: Button):
        modal = UpscaleOptionsModal(self.target_message, self.image_url, self.selected_type)
        await interaction.response.send_modal(modal)
        await self.original_interaction.edit_original_response(view=None)
    async def on_timeout(self):
        await self.original_interaction.edit_original_response(content="Upscale options timed out.", view=None)

class DescribeControlView(View):
    def __init__(self, original_interaction: discord.Interaction, image_url: str):
        super().__init__(timeout=300)
        self.original_interaction = original_interaction
        self.image_url = image_url
        self.selected_description_type = "prompt"
        self.selected_language = "english"
        self.type_select = Select(placeholder="Choose a description type...", options=[discord.SelectOption(label="Prompt", value="prompt", default=True), discord.SelectOption(label="Natural Language", value="natural")])
        self.type_select.callback = self.type_select_callback
        self.add_item(self.type_select)
        self.language_select = Select(placeholder="Choose a language...", options=[discord.SelectOption(label="English", value="english", default=True), discord.SelectOption(label="French", value="french")])
        self.language_select.callback = self.language_select_callback
        self.add_item(self.language_select)
    async def type_select_callback(self, interaction: discord.Interaction):
        self.selected_description_type = self.type_select.values[0]
        await interaction.response.defer()
    async def language_select_callback(self, interaction: discord.Interaction):
        self.selected_language = self.language_select.values[0]
        await interaction.response.defer()
    @discord.ui.button(label="Describe Image", style=discord.ButtonStyle.success, row=2)
    async def start_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Starting image analysis...", view=None)
        args = {"input_image_url": self.image_url, "description_type": self.selected_description_type, "language": self.selected_language}
        await _execute_and_process_tool_call(interaction, "describe_image", args)
    async def on_timeout(self):
        await self.original_interaction.edit_original_response(content="Describe options timed out.", view=None)

async def setup(bot: commands.Bot, api_client: APIClient):
    global _bot_instance, _api_client_instance
    _bot_instance = bot
    _api_client_instance = api_client
    async def style_names_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await _get_choices_for_tool_param('generate_image', 'style_names', current)
    async def render_type_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        return await _get_choices_for_tool_param('generate_image', 'render_type', current)
    
    @bot.tree.command(name="image", description="Generates an image using an AI model.")
    @app_commands.describe(prompt="A detailed description of the desired image.", enhance_prompt="Let the AI improve your prompt before generation.", seed="A specific seed to reproduce an image.")
    @app_commands.choices(aspect_ratio=[
        app_commands.Choice(name="Square (1:1)", value="1:1"),
        app_commands.Choice(name="Landscape (16:9)", value="16:9"),
        app_commands.Choice(name="Portrait (9:16)", value="9:16"),
        app_commands.Choice(name="Photo (4:3)", value="4:3"),
        app_commands.Choice(name="Tall Photo (3:4)", value="3:4"),
    ])
    @app_commands.autocomplete(style_names=style_names_autocomplete, render_type=render_type_autocomplete)
    async def image(interaction: discord.Interaction, prompt: str, negative_prompt: Optional[str] = None, style_names: Optional[str] = None, aspect_ratio: Optional[str] = None, render_type: Optional[str] = None, enhance_prompt: Optional[bool] = None, seed: Optional[int] = None):
        args = {
            "prompt": prompt, "negative_prompt": negative_prompt, "style_names": style_names, "aspect_ratio": aspect_ratio, 
            "render_type": render_type, "enhance_prompt": enhance_prompt, "seed": seed
        }
        args = {k: v for k, v in args.items() if v is not None}
        if 'style_names' in args and args['style_names']: 
            args['style_names'] = [s.strip() for s in args['style_names'].split(',') if s.strip()]
        await _execute_and_process_tool_call(interaction, "generate_image", args)

    @bot.tree.context_menu(name="Upscale Image")
    async def upscale_context_menu(interaction: discord.Interaction, target: discord.Message):
        image_url = _find_image_url_in_message(target)
        if not image_url:
            await interaction.response.send_message("I couldn't find an image in that message.", ephemeral=True)
            return
        definitions = await _get_tool_definitions_with_cache()
        tool_def = next((t for t in definitions if t.get("name") == "upscale_image"), None)
        choices = tool_def.get("inputSchema", {}).get("properties", {}).get("upscale_type", {}).get("enum", []) if tool_def else []
        view = UpscaleControlView(interaction, target, image_url, choices)
        await interaction.response.send_message("Select upscale options:", view=view, ephemeral=True)

    @bot.tree.context_menu(name="Describe Image")
    async def describe_context_menu(interaction: discord.Interaction, target: discord.Message):
        image_url = _find_image_url_in_message(target)
        if not image_url:
            await interaction.response.send_message("I couldn't find an image in that message.", ephemeral=True)
            return
        view = DescribeControlView(interaction, image_url)
        await interaction.response.send_message("Ready to describe this image:", view=view, ephemeral=True)

    bot.add_listener(on_message)
    
    @bot.event
    async def on_ready():
        await bot.tree.sync()
        logger.info(f"Command tree synced for {bot.user}.")

    logger.info("Event handler setup complete.")