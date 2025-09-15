####
# discord_bot_launcher/bot_process.py
####
import asyncio
import sys
import requests
import discord
import argparse
import json
import traceback
import httpx
import re
import io
import ast
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

# --- Constants ---
DISCORD_MSG_LIMIT = 2000
STREAM_EDIT_DELAY = 1.3 # Seconds between message edits to avoid rate limits

# --- Logging Configuration ---
BOT_ID = None
BOT_CONFIG = {}
API_BASE_URL = None
LOGS_API_URL = None
GATEKEEPER_API_URL = None
DISPATCH_API_URL = None
ACKNOWLEDGE_API_URL = None
SYNTHESIZE_API_URL = None
ARCHIVE_API_URL = None
GATEKEEPER_HISTORY_LIMIT = 5
CONVERSATION_HISTORY_LIMIT = 15


def send_log(level: str, source: str, payload: Dict):
    """
    Sends a structured log to both stdout (for the launcher) and the API (for the UI).
    """
    try:
        log_string = f"[{level.upper()}] [{source.upper()}] {json.dumps(payload)}"
        print(log_string, file=sys.stdout, flush=True)
    except Exception:
        print(f"[{level.upper()}] [{source.upper()}] (Payload not serializable)", file=sys.stdout, flush=True)

    if not LOGS_API_URL: return
    try:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source.upper(),
            "level": level.upper(),
            "message": json.dumps(payload)
        }
        requests.post(LOGS_API_URL, json=log_entry, timeout=2)
    except Exception as e:
        print(f"[ERROR] [LOG_SUBMISSION] Failed to send log to API: {e}", file=sys.stdout, flush=True)

# --- Internal & External Tool Handling ---
def _resolve_user_identifier(guild: discord.Guild, user_identifier: str) -> Optional[discord.Member]:
    """Helper function to find a member in a guild by mention, name, or display name."""
    mention_match = re.match(r'<@!?(\d+)>', user_identifier)
    if mention_match:
        user_id = int(mention_match.group(1))
        return guild.get_member(user_id)

    for member in guild.members:
        if member.display_name.lower() == user_identifier.lower() or member.name.lower() == user_identifier.lower():
            return member

    return None

INTERNAL_TOOLS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_server_channels",
            "description": "Get a list of all visible text channels on the current Discord server.",
            "parameters": { "type": "object", "properties": {} }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_info",
            "description": "Get detailed public information about a specific user on this Discord server. Can accept a username, a display name (nickname), or a direct @mention.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_identifier": {
                        "type": "string",
                        "description": "The name, nickname, or the full mention string (e.g., '<@12345...>') of the user to look up."
                    }
                },
                "required": ["user_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_server_layout",
            "description": "Get a comprehensive layout of the current Discord server, including categories and the channels within them, their type, and topic.",
            "parameters": { "type": "object", "properties": {} }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Retrieves your stored knowledge and behavioral instructions about a user on this server. Use this to learn about users before interacting with them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_identifier": {
                        "type": "string",
                        "description": "The name, nickname, or mention of the user whose profile you want to retrieve."
                    }
                },
                "required": ["user_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_user_note",
            "description": "Saves a single factual note about a user. Use this to remember important information that you can retrieve later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_identifier": {
                        "type": "string",
                        "description": "The name, nickname, or mention of the user this note is about."
                    },
                    "note": {
                        "type": "string",
                        "description": "The text of the note to be saved. Must be a single, concise fact."
                    },
                    "reliability_score": {
                        "type": "integer",
                        "description": "An integer from 0 to 100 representing your confidence in the note's accuracy. E.g., 90 if the user stated it themselves, 50 if reported by a third party, 20 if it seems like a joke."
                    }
                },
                "required": ["user_identifier", "note", "reliability_score"]
            }
        }
    }
]

DISPATCHER_INTERNAL_TOOLS_DEFINITIONS = [
    tool for tool in INTERNAL_TOOLS_DEFINITIONS if tool.get("function", {}).get("name") != "save_user_note"
]

def _tool_list_server_channels(message: discord.Message, **kwargs) -> str:
    if not isinstance(message.channel, discord.TextChannel) or not message.guild:
        return "This command can only be used in a server channel, not in a Direct Message."

    text_channels = [f"#{channel.name}" for channel in message.guild.text_channels]
    return f"Here are the text channels on this server:\n" + "\n".join(text_channels) if text_channels else "No text channels found on this server."

def _tool_get_user_info(message: discord.Message, user_identifier: str) -> str:
    if not message.guild:
        return "This tool can only be used in a server."

    target_member = _resolve_user_identifier(message.guild, user_identifier)

    if not target_member:
        return f"User '{user_identifier}' not found on this server."

    roles = [role.name for role in target_member.roles if role.name != "@everyone"]
    joined_at_str = target_member.joined_at.strftime("%Y-%m-%d %H:%M:%S UTC") if target_member.joined_at else "Unknown"

    info = [
        f"## User Information for {target_member.display_name}",
        f"- Display Name (Nickname): {target_member.display_name}",
        f"- Username: {target_member.name}",
        f"- User ID: {target_member.id}",
        f"- Is Bot: {'Yes' if target_member.bot else 'No'}",
        f"- Status: {str(target_member.status).title()}",
        f"- Server Join Date: {joined_at_str}",
        f"- Roles: {', '.join(roles) if roles else 'None'}"
    ]
    return "\n".join(info)

def _tool_get_server_layout(message: discord.Message, **kwargs) -> str:
    if not message.guild:
        return "This tool can only be used in a server."

    layout_parts = [f"# Layout for Server: {message.guild.name}\n"]

    for category, channels in message.guild.by_category():
        category_name = category.name if category else "Uncategorized"
        layout_parts.append(f"## Category: {category_name}")

        if not channels:
            layout_parts.append("- (No channels in this category)")
            continue

        for channel in channels:
            channel_type = str(channel.type).title().replace('_', ' ')
            layout_parts.append(f"- **#{channel.name}** (Type: {channel_type})")

            if isinstance(channel, discord.TextChannel) and channel.topic:
                layout_parts.append(f"  - Topic: {channel.topic}")

            if isinstance(channel, discord.VoiceChannel):
                if channel.members:
                    members_info = [f"{m.display_name}" for m in channel.members]
                    layout_parts.append(f"  - Members Connected: {len(channel.members)} -> {', '.join(members_info)}")
                else:
                    layout_parts.append("  - Members Connected: 0")

    return "\n".join(layout_parts)

def _tool_get_user_profile(message: discord.Message, user_identifier: str) -> str:
    if not message.guild:
        return "This tool is only available on a server."

    target_member = _resolve_user_identifier(message.guild, user_identifier)
    if not target_member:
        return f"User '{user_identifier}' could not be found on this server."

    api_url = f"{API_BASE_URL}/bots/{BOT_ID}/servers/{message.guild.id}/users/{target_member.id}/profile"
    
    payload = {
        "username": target_member.name,
        "display_name": target_member.display_name
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        instructions = data.get("behavioral_instructions", "No specific instructions provided.")
        notes = data.get("notes", [])

        result_parts = [f"## Profile for {target_member.display_name} (@{target_member.name})"]
        result_parts.append(f"**My Instructions:** {instructions}")

        if not notes:
            result_parts.append("\n**Stored Notes:** I have no notes on this user yet.")
        else:
            result_parts.append("\n**Stored Notes:**")
            sorted_notes = sorted(notes, key=lambda x: x['reliability_score'], reverse=True)
            for note in sorted_notes:
                ts = datetime.fromisoformat(note['created_at']).strftime('%Y-%m-%d')
                result_parts.append(f"- (Reliability: {note['reliability_score']}%) {note['note_content']} [Saved on {ts}]")

        return "\n".join(result_parts)

    except requests.HTTPError as e:
        return f"API Error: Failed to retrieve profile. Status: {e.response.status_code}, Details: {e.response.text}"
    except Exception as e:
        return f"An unexpected error occurred while fetching the user profile: {e}"

def _tool_save_user_note(message: discord.Message, user_identifier: str, note: str, reliability_score: int) -> str:
    if not message.guild:
        return "This tool is only available on a server."

    target_member = _resolve_user_identifier(message.guild, user_identifier)
    if not target_member:
        return f"User '{user_identifier}' could not be found on this server. Note was not saved."

    api_url = f"{API_BASE_URL}/bots/{BOT_ID}/servers/{message.guild.id}/users/{target_member.id}/notes"

    payload = {
        "user_discord_id": str(target_member.id),
        "server_discord_id": str(message.guild.id),
        "author_discord_id": str(message.author.id),
        "note_content": note,
        "reliability_score": reliability_score
    }

    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status()
        return f"Success. The note about {target_member.display_name} has been saved."
    except requests.HTTPError as e:
        return f"API Error: Failed to save note. Status: {e.response.status_code}, Details: {e.response.text}"
    except Exception as e:
        return f"An unexpected error occurred while saving the note: {e}"


INTERNAL_TOOL_IMPLEMENTATIONS = {
    "list_server_channels": _tool_list_server_channels,
    "get_user_info": _tool_get_user_info,
    "get_server_layout": _tool_get_server_layout,
    "get_user_profile": _tool_get_user_profile,
    "save_user_note": _tool_save_user_note,
}

async def _call_external_tool(tool_call: Dict) -> Dict:
    tool_name = tool_call.get("function", {}).get("name")
    arguments = tool_call.get("function", {}).get("arguments", {})
    tool_api_url = f"{API_BASE_URL}/tools/call"

    send_log("info", "external_tool_call", {"tool_name": tool_name, "url": tool_api_url})

    payload = {
        "bot_id": BOT_ID,
        "tool_name": tool_name,
        "arguments": arguments
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(tool_api_url, json=payload)
            response.raise_for_status()
            result = response.json()
            if isinstance(result, dict) and "content" in result and isinstance(result.get("content"), list):
                return result
            return {"content": [{"type": "text", "text": str(result)}]}
    except httpx.HTTPStatusError as e:
        error_detail = e.response.json().get("detail", e.response.text)
        send_log("error", "external_tool_api_error", {"tool_name": tool_name, "status": e.response.status_code, "detail": error_detail})
        return {"content": [{"type": "text", "text": f"API Error executing tool {tool_name}: {error_detail}"}]}
    except Exception as e:
        send_log("error", "external_tool_general_error", {"tool_name": tool_name, "error": str(e)})
        return {"content": [{"type": "text", "text": f"General Error executing tool {tool_name}: {e}"}]}

async def _dispatch_tool_call(tool_call: Dict, message: discord.Message) -> str:
    tool_name = tool_call.get("function", {}).get("name")

    if tool_name in INTERNAL_TOOL_IMPLEMENTATIONS:
        send_log("info", "internal_tool_call", {"tool_name": tool_name})
        try:
            arguments = tool_call.get("function", {}).get("arguments", {})
            result_text = INTERNAL_TOOL_IMPLEMENTATIONS[tool_name](message=message, **arguments)
            return json.dumps({"content": [{"type": "text", "text": result_text}]})
        except Exception as e:
            send_log("error", "internal_tool_error", {"tool_name": tool_name, "error": str(e)})
            return json.dumps({"content": [{"type": "text", "text": f"Error executing tool {tool_name}: {e}"}]})
    else:
        result_dict = await _call_external_tool(tool_call)
        return json.dumps(result_dict)


# --- Conversation State & History Management ---
chat_histories: Dict[int, List[Dict[str, Any]]] = {}

# --- Robust Message Management & Streaming Logic ---
class MessageStreamManager:
    def __init__(self, original_message: discord.Message, client: discord.Client, files: Optional[List[discord.File]] = None):
        self.client = client
        self.original_message = original_message
        self.channel = original_message.channel
        self.files = files or []
        self.files_sent = False
        self.buffer = ""
        self.current_message: Optional[discord.Message] = None
        self.last_edit_time = datetime.fromtimestamp(0, tz=timezone.utc)
        self.edit_task: Optional[asyncio.Task] = None

    def _find_natural_break(self, text: str, max_len: int) -> int:
        if len(text) <= max_len: return len(text)
        delimiters = ['\n\n', '\n', '. ', '! ', '? ', ' ', '-']
        best_pos = -1
        for delimiter in delimiters:
            pos = text.rfind(delimiter, 0, max_len)
            if pos != -1:
                best_pos = pos + len(delimiter)
                break
        return best_pos if best_pos != -1 else max_len

    async def _execute_edit(self):
        content_to_send = self.buffer.strip()
        if not content_to_send and self.current_message:
            content_to_send = "..."
            self.buffer = ""

        if not content_to_send: return

        try:
            if self.current_message:
                if self.current_message.content != content_to_send:
                    await self.current_message.edit(content=content_to_send)
            else:
                files_to_send = self.files if not self.files_sent else []
                self.current_message = await send_response(self.original_message, content_to_send, files=files_to_send)
                if files_to_send:
                    self.files_sent = True
            self.last_edit_time = datetime.now(timezone.utc)
        except discord.errors.NotFound:
            files_to_send = self.files if not self.files_sent else []
            self.current_message = await send_response(self.original_message, content_to_send, files=files_to_send)
            if files_to_send:
                    self.files_sent = True
        except Exception as e:
            send_log("error", "discord_edit_error", {"error": str(e), "content_length": len(content_to_send)})

    async def _schedule_edit(self):
        if self.edit_task and not self.edit_task.done(): self.edit_task.cancel()
        delay = STREAM_EDIT_DELAY - (datetime.now(timezone.utc) - self.last_edit_time).total_seconds()
        if delay <= 0:
            await self._execute_edit()
        else:
            self.edit_task = asyncio.create_task(self._delayed_edit(delay))

    async def _delayed_edit(self, delay: float):
        await asyncio.sleep(delay)
        await self._execute_edit()

    async def add_text(self, text: str):
        if not text: return
        self.buffer += text
        while len(self.buffer) > DISCORD_MSG_LIMIT:
            split_pos = self._find_natural_break(self.buffer, DISCORD_MSG_LIMIT)
            part_to_send = self.buffer[:split_pos]
            self.buffer = self.buffer[split_pos:]
            await self.finalize_current_message_with_content(part_to_send)
        if self.buffer:
            await self._schedule_edit()

    async def finalize_current_message_with_content(self, content: str):
        if self.edit_task and not self.edit_task.done(): self.edit_task.cancel()
        self.buffer = content
        if self.buffer.strip(): await self._execute_edit()
        self.buffer = ""
        self.current_message = None

    async def finalize(self):
        if self.edit_task and not self.edit_task.done(): self.edit_task.cancel()
        if self.buffer.strip(): await self._execute_edit()
        self.buffer = ""
        self.current_message = None

async def send_as_file(channel: discord.TextChannel, code_block: str):
    match = re.match(r'```(\w*)\s*\n?([\sS]*?)```', code_block, re.DOTALL)
    lang, code = (match.groups() if match else ('txt', code_block.strip('`')))
    if not code.strip(): return
    with io.BytesIO(code.encode('utf-8')) as f:
        await channel.send(file=discord.File(f, filename=f"code_block.{lang or 'txt'}"))

# --- Main Application Logic ---
async def _get_formatted_channel_history(channel: discord.abc.Messageable, limit: int) -> List[str]:
    if limit <= 0: return []
    history_messages = []
    try:
        async for msg in channel.history(limit=limit, before=None, oldest_first=False):
            history_messages.append(f"[{msg.author.display_name} (@{msg.author.name})]: {msg.content}")
    except Exception as e:
        send_log("warning", "history_fetch_failed", {"channel_id": channel.id, "error": str(e)})
        return []
    history_messages.reverse()
    return history_messages

async def _sync_user_profile(message: discord.Message):
    """Fire-and-forget call to sync the user's profile info (names)."""
    server_id = message.guild.id if message.guild else 0
    api_url = f"{API_BASE_URL}/bots/{BOT_ID}/servers/{server_id}/users/{message.author.id}/profile"
    payload = {"username": message.author.name, "display_name": message.author.display_name}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(api_url, json=payload)
            response.raise_for_status()
        send_log("info", "profile_sync_success", {"user_id": message.author.id})
    except Exception as e:
        error_details = {"error": str(e), "user_id": message.author.id}
        if isinstance(e, httpx.HTTPStatusError):
            error_details["status_code"] = e.response.status_code
            error_details["response_body"] = e.response.text
        send_log("warning", "profile_sync_failed", error_details)

async def send_response(original_message: discord.Message, content: str, files: Optional[List[discord.File]] = None) -> Optional[discord.Message]:
    """Sends a response, replying only if new messages have appeared in the channel."""
    try:
        last_messages = [msg async for msg in original_message.channel.history(limit=1)]
        if not last_messages or last_messages[0].id != original_message.id:
            return await original_message.reply(content, files=files)
        else:
            return await original_message.channel.send(content, files=files)
    except Exception as e:
        print(f"[ERROR] [SEND_RESPONSE_FAILED] {str(e)}", file=sys.stdout, flush=True)
        return None

def _get_tool_config(tool_name: str) -> Dict[str, Any]:
    """Finds a tool's specific configuration from the global BOT_CONFIG."""
    for server in BOT_CONFIG.get("mcp_servers", []):
        config = server.get("configuration", {})
        if config and tool_name in config.get("tool_config", {}):
            return config["tool_config"][tool_name]
    return {}

def _is_slow_tool_call(tool_calls: List[Dict]) -> bool:
    """Checks if any tool in a list is configured as slow."""
    return any(_get_tool_config(call["function"]["name"]).get("is_slow", False) for call in tool_calls)

def _get_reaction_for_tools(tool_calls: List[Dict]) -> str:
    """Gets a representative reaction emoji for a list of tool calls."""
    for call in tool_calls:
        emoji = _get_tool_config(call["function"]["name"]).get("reaction_emoji")
        if emoji:
            return emoji
    return "🛠️" # Default tool emoji

def _try_parse_error_from_tool_text(text: str) -> Optional[str]:
    """
    Safely parses a string that might be a Python dict representation of an error.
    Returns a clean error message string if found, otherwise None.
    """
    clean_text = text.strip()
    if not (clean_text.startswith("{") and clean_text.endswith("}")):
        return None
    try:
        error_dict = ast.literal_eval(clean_text)
        if isinstance(error_dict, dict) and 'error' in error_dict and 'message' in error_dict['error']:
            return f"The tool returned an error: {error_dict['error']['message']}"
    except (ValueError, SyntaxError, MemoryError, TypeError):
        return None
    return None

def create_discord_client():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    client = discord.Client(intents=intents)

    def _extract_json_objects(json_buffer: str) -> Tuple[str, List[Dict]]:
        parsed_objects, cursor = [], 0
        while True:
            start_index = json_buffer.find('{', cursor)
            if start_index == -1: break
            brace_level, end_index = 0, -1
            for i in range(start_index, len(json_buffer)):
                if json_buffer[i] == '{': brace_level += 1
                elif json_buffer[i] == '}': brace_level -= 1
                if brace_level == 0: end_index = i + 1; break
            if end_index == -1: break
            try:
                data = json.loads(json_buffer[start_index:end_index])
                parsed_objects.append(data)
                cursor = end_index
            except json.JSONDecodeError: cursor = start_index + 1
        return json_buffer[cursor:], parsed_objects

    async def _process_text_with_state_machine(
        text_to_process: str, parsing_mode: str, code_block_buffer: str, stream_manager: MessageStreamManager,
    ) -> Tuple[str, str]:
        while text_to_process:
            if parsing_mode == 'text':
                think_pos, code_pos = text_to_process.find('<think>'), text_to_process.find('```')
                if think_pos != -1 and (code_pos == -1 or think_pos < code_pos):
                    await stream_manager.add_text(text_to_process[:think_pos])
                    text_to_process = text_to_process[think_pos + len('<think>'):]; parsing_mode = 'think'
                elif code_pos != -1 and (think_pos == -1 or code_pos < think_pos):
                    await stream_manager.add_text(text_to_process[:code_pos]); await stream_manager.finalize()
                    text_to_process = text_to_process[code_pos + len('```'):]; parsing_mode = 'code'
                else:
                    await stream_manager.add_text(text_to_process); text_to_process = ""
            elif parsing_mode == 'think':
                end_think_pos = text_to_process.find('</think>')
                if end_think_pos != -1: text_to_process = text_to_process[end_think_pos + len('</think>'):]; parsing_mode = 'text'
                else: text_to_process = ""
            elif parsing_mode == 'code':
                end_code_pos = text_to_process.find('```')
                if end_code_pos != -1:
                    code_block_buffer += text_to_process[:end_code_pos]
                    await send_as_file(stream_manager.channel, f"```{code_block_buffer}```"); code_block_buffer = ""
                    text_to_process = text_to_process[end_code_pos + len('```'):]; parsing_mode = 'text'
                else: code_block_buffer += text_to_process; text_to_process = ""
            else: text_to_process = ""
        return parsing_mode, code_block_buffer
    async def call_archivist(chat_context_payload: Dict, final_bot_response: str):
        if not final_bot_response.strip() or not ARCHIVE_API_URL: return
        payload = {"chat_context": chat_context_payload, "final_bot_response": final_bot_response}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(ARCHIVE_API_URL, json=payload)
        except Exception as e:
            send_log("error", "archivist_call_failed", {"error": str(e)})

    async def _download_image_to_discord_file(image_url: str) -> Tuple[Optional[discord.File], Optional[str]]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                img_response = await http_client.get(image_url)
                img_response.raise_for_status()
                file_object = discord.File(io.BytesIO(img_response.content), filename=image_url.split('/')[-1])
                return file_object, None
        except Exception as img_exc:
            error_msg = f"Failed to retrieve the image from {image_url}."
            send_log("error", "image_download_failed", {"url": image_url, "error": str(img_exc)})
            return None, error_msg

    async def execute_tools_and_synthesize(message: discord.Message, local_history: List[Dict], base_payload: Dict, tool_calls: List[Dict]):
        """Handles tool execution, synthesis, and final response sending."""
        files_to_attach: List[discord.File] = []
        synthesizer_payload, final_response, cleaned_final_response = {}, "", ""

        try:
            if tool_calls:
                assistant_tool_call_msg = {"role": "assistant", "content": "", "tool_calls": tool_calls}
                local_history.append(assistant_tool_call_msg)
                
                raw_tool_results = await asyncio.gather(*[_dispatch_tool_call(call, message) for call in tool_calls])
                
                images_found = 0
                for i, call in enumerate(tool_calls):
                    raw_result_str, text_parts, has_media_output = raw_tool_results[i], [], False
                    try:
                        content_list = json.loads(raw_result_str).get("content", [])
                        for block in content_list:
                            image_url, text_content = None, None
                            
                            if block.get("type") == "image" and block.get("source"):
                                image_url = block["source"]
                            elif block.get("type") == "text" and block.get("text"):
                                text_content = str(block["text"])
                                # Robustness: Check if text content is actually an image URL
                                if re.match(r'^https?://.*\.(png|jpg|jpeg|webp|gif)$', text_content.strip(), re.IGNORECASE):
                                    image_url = text_content.strip()

                            if image_url:
                                images_found += 1
                                has_media_output = True
                                image_file, error_msg = await _download_image_to_discord_file(image_url)
                                if image_file:
                                    files_to_attach.append(image_file)
                                if error_msg:
                                    text_parts.append(error_msg)
                            
                            if text_content and not image_url: # Process text only if it wasn't treated as an image URL
                                parsed_error = _try_parse_error_from_tool_text(text_content)
                                if parsed_error:
                                    text_parts.append(parsed_error)
                                    send_log("warning", "tool_returned_error", {"tool_name": call.get("function", {}).get("name"), "error": parsed_error})
                                else:
                                    text_parts.append(text_content)
                    except (json.JSONDecodeError, AttributeError):
                            text_parts.append(str(raw_result_str))
                    
                    tool_content_result = "\n".join(text_parts).strip()
                    if has_media_output and not tool_content_result:
                        tool_content_result = "[An image was generated and will be displayed with the final message.]"
                    elif not tool_content_result:
                        tool_content_result = "[Tool executed successfully with no textual output.]"

                    local_history.append({ "role": "tool", "content": tool_content_result })
                
                send_log("info", "tool_execution_complete", {"count": len(tool_calls), "images": images_found})

            stream_manager = MessageStreamManager(message, client, files=files_to_attach)
            send_log("info", "synthesizer_call_preparation", {"history_len": len(local_history)})
            synthesizer_payload = {
                "bot_id": base_payload["bot_id"],
                "messages": local_history,
                "user_context": base_payload["user_context"],
                "channel_context": base_payload["channel_context"]
            }

            json_buffer, text_buffer, code_buffer, parsing_mode = "", "", "", "text"
            async with httpx.AsyncClient(timeout=300.0) as http_client, http_client.stream("POST", SYNTHESIZE_API_URL, json=synthesizer_payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    json_buffer += chunk
                    json_buffer, parsed_objects = _extract_json_objects(json_buffer)
                    for data in parsed_objects:
                        if "error" in data: raise Exception(data["error"])
                        if content := data.get("message", {}).get("content"):
                            final_response += content; text_buffer += content
                    if (last_nl := text_buffer.rfind('\n')) != -1:
                        text_now, text_buffer = text_buffer[:last_nl + 1], text_buffer[last_nl + 1:]
                        parsing_mode, code_buffer = await _process_text_with_state_machine(text_now, parsing_mode, code_buffer, stream_manager)

            if text_buffer: _, code_buffer = await _process_text_with_state_machine(text_buffer, parsing_mode, code_buffer, stream_manager)
            if code_buffer: await send_as_file(stream_manager.channel, f"```{code_buffer}```")

            await stream_manager.finalize()

            if final_response.strip():
                cleaned_final_response = re.sub(r'<think>.*?</think>', '', final_response, flags=re.DOTALL).strip()
                if cleaned_final_response:
                    local_history.append({"role": "assistant", "content": cleaned_final_response})
            
            chat_histories[message.channel.id] = local_history

        finally:
            if synthesizer_payload and cleaned_final_response:
                asyncio.create_task(call_archivist(synthesizer_payload, cleaned_final_response))
            send_log("info", "turn_complete", {"channel_id": message.channel.id})
    
    @client.event
    async def on_ready(): send_log("info", "process_status", {"status": "online", "discord_user": str(client.user)})

    @client.event
    async def on_message(message: discord.Message):
        if message.author == client.user: return
        
        is_dm, is_mentioned = isinstance(message.channel, discord.DMChannel), client.user.mentioned_in(message)
        passive_listening = BOT_CONFIG.get("passive_listening_enabled", False)

        should_process = False
        if is_dm or is_mentioned: should_process = True
        elif passive_listening and not is_dm:
            history = await _get_formatted_channel_history(message.channel, GATEKEEPER_HISTORY_LIMIT)
            payload = {"bot_id": BOT_ID, "messages": [{"role": "user", "content": f"[{message.author.display_name}]: {message.content}"}], "channel_history": history}
            try:
                async with httpx.AsyncClient(timeout=20.0) as http_client:
                    response = await http_client.post(GATEKEEPER_API_URL, json=payload)
                    response.raise_for_status()
                    if response.json().get("should_respond"): should_process = True
            except Exception as e: send_log("error", "gatekeeper_call_failed", {"error": str(e)})

        if not should_process: return
        
        asyncio.create_task(_sync_user_profile(message))
        
        current_reaction = None
        try:
            await message.add_reaction("🤔"); current_reaction = "🤔"
            
            channel_history = await _get_formatted_channel_history(message.channel, CONVERSATION_HISTORY_LIMIT)
            uploaded_files = await handle_attachments(message)
            
            cleaned_content = re.sub(f'<@!?{client.user.id}>', '', message.content).strip()
            if not cleaned_content and not uploaded_files: return

            persistent_history = chat_histories.get(message.channel.id, [])
            # --- START RACE CONDITION FIX ---
            local_history = list(persistent_history)
            # --- END RACE CONDITION FIX ---
            local_history.append({"role": "user", "content": f"[{message.author.display_name}]: {cleaned_content}"})
            if len(local_history) > 20:
                local_history = local_history[-20:]

            user_context = {"discord_id": str(message.author.id), "name": message.author.name, "display_name": message.author.display_name}
            channel_context = {"context_type": "DIRECT_MESSAGE", "channel_id": str(message.channel.id)}
            if message.guild:
                channel_context.update({"context_type": "SERVER_CHANNEL", "server_id": str(message.guild.id), "server_name": message.guild.name, "channel_name": message.channel.name})

            base_payload = {"bot_id": BOT_ID, "messages": local_history, "user_context": user_context, "channel_context": channel_context, "tools": DISPATCHER_INTERNAL_TOOLS_DEFINITIONS, "channel_history": channel_history, "attached_files": uploaded_files or None}

            await message.remove_reaction(current_reaction, client.user)
            await message.add_reaction("💬"); current_reaction = "💬"

            dispatch_decision = {}
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                response = await http_client.post(DISPATCH_API_URL, json=base_payload)
                response.raise_for_status()
                dispatch_decision = response.json()
            
            tool_calls = dispatch_decision.get("tool_calls") if isinstance(dispatch_decision, dict) else None

            if tool_calls:
                is_slow = _is_slow_tool_call(tool_calls)
                reaction = _get_reaction_for_tools(tool_calls)
                await message.remove_reaction(current_reaction, client.user)
                await message.add_reaction(reaction); current_reaction = reaction

                if is_slow:
                    ack_payload = {"bot_id": BOT_ID, "user_context": user_context, "tool_name": tool_calls[0]["function"]["name"]}
                    async with httpx.AsyncClient(timeout=20.0) as http_client:
                        ack_res = await http_client.post(ACKNOWLEDGE_API_URL, json=ack_payload)
                        if ack_res.is_success:
                            await send_response(message, ack_res.json().get("acknowledgement_message", "..."))
                    
                    asyncio.create_task(execute_tools_and_synthesize(message, local_history, base_payload, tool_calls))
                else:
                    await execute_tools_and_synthesize(message, local_history, base_payload, tool_calls)
            else:
                await message.remove_reaction(current_reaction, client.user); current_reaction=None
                await execute_tools_and_synthesize(message, local_history, base_payload, [])

        except Exception as e:
            send_log("error", "on_message_error", {"error": str(e), "traceback": traceback.format_exc()})
            await send_response(message, "I'm sorry, a critical error occurred while processing your request.")
        finally:
            if current_reaction:
                try: await message.remove_reaction(current_reaction, client.user)
                except: pass
        
    async def handle_attachments(message: discord.Message) -> List[Dict]:
        if not message.attachments: return []
        upload_url = f"{API_BASE_URL}/files/upload/bot/{BOT_ID}"
        successful_uploads = []
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            for attachment in message.attachments:
                try:
                    files = {"file": (attachment.filename, await attachment.read(), attachment.content_type)}
                    data = {"owner_discord_id": str(message.author.id)}
                    response = await http_client.post(upload_url, files=files, data=data)
                    response.raise_for_status()
                    file_data = response.json()
                    successful_uploads.append({"uuid": file_data["uuid"], "filename": file_data["filename"], "file_family": file_data["file_family"]})
                    await message.add_reaction("💾")
                except Exception as e:
                    await message.add_reaction("❌")
        return successful_uploads

    return client

def main():
    global BOT_ID, BOT_CONFIG, API_BASE_URL, LOGS_API_URL, GATEKEEPER_API_URL, DISPATCH_API_URL, ACKNOWLEDGE_API_URL, SYNTHESIZE_API_URL, ARCHIVE_API_URL, GATEKEEPER_HISTORY_LIMIT, CONVERSATION_HISTORY_LIMIT
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-id", type=int, required=True)
    parser.add_argument("--gatekeeper-history-limit", type=int, default=5)
    parser.add_argument("--conversation-history-limit", type=int, default=15)
    args = parser.parse_args()
    BOT_ID, GATEKEEPER_HISTORY_LIMIT, CONVERSATION_HISTORY_LIMIT = args.bot_id, args.gatekeeper_history_limit, args.conversation_history_limit
    
    API_BASE_URL = "http://app:8000/api"
    LOGS_API_URL = f"{API_BASE_URL}/bots/{BOT_ID}/logs"
    GATEKEEPER_API_URL = f"{API_BASE_URL}/chat/gatekeeper"
    DISPATCH_API_URL = f"{API_BASE_URL}/chat/dispatch"
    ACKNOWLEDGE_API_URL = f"{API_BASE_URL}/chat/acknowledge"
    SYNTHESIZE_API_URL = f"{API_BASE_URL}/chat/"
    ARCHIVE_API_URL = f"{API_BASE_URL}/chat/archive"

    send_log("info", "process_status", {"status": "starting"})
    
    try:
        config_res = requests.get(f"{API_BASE_URL}/bots/{BOT_ID}", timeout=10)
        config_res.raise_for_status()
        BOT_CONFIG = config_res.json()
        bot_token = BOT_CONFIG.get("discord_token")
        if not bot_token or bot_token.startswith("PLACEHOLDER"): sys.exit(0)
    except Exception as e:
        send_log("critical", "startup_error", {"message": f"Could not fetch bot config: {e}"})
        sys.exit(1)

    client = create_discord_client()
    try: client.run(bot_token)
    except discord.errors.LoginFailure: send_log("critical", "runtime_error", {"message": "Login failed. Invalid token."}); sys.exit(1)
    except Exception as e: send_log("critical", "runtime_error", {"message": str(e)}); sys.exit(1)

if __name__ == "__main__":
    main()