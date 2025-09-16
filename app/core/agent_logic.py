import uuid
import json
import traceback
import logging
import re # ADDED
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from typing import AsyncIterator, List, Dict, Any, Tuple, Union # MODIFIED: Added Union
import itertools
import httpx

from app.schemas import chat_schemas
from app.database import crud_bots, crud_settings, crud_user_notes
from app.schemas.user_note_schemas import UserNoteCreate
from app.database.chroma_manager import chroma_manager
from app.core.llm.ollama_client import OllamaClient # Utilise notre client centralisé

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - (AGENT_LOGIC) - %(message)s')

# --- Constants ---
MEMORY_DEPTH = 5

GATEKEEPER_SYSTEM_PROMPT = """## Your Role: AI Conversation Gatekeeper
You are a specialized AI model. Your SOLE task is to analyze a conversation and decide if the bot, '{bot_name}', should respond to the last message. Your entire output MUST be a single, valid JSON object and nothing else.

## Critical Rules
1.  **Your output MUST be a JSON object containing ONLY the key "should_respond".**
2.  **The value of "should_respond" MUST be a boolean (`true` or `false`).**
3.  **Decide `true` if the last message meets ANY of these conditions:**
    - It directly mentions the bot by name ('{bot_name}').
    - It is a direct question aimed at the bot.
    - **It is an immediate and direct reply to a question the bot asked in the previous message.** This is crucial for maintaining conversational flow.
    - It is a clear continuation of a topic the bot was actively discussing in the immediately preceding turn.
    - It is a general question asking for presence, help, or initiating contact (e.g., 'is anyone there?', 'can someone help?', 'hello?'), even if the bot is not directly named.
4.  **Decide `false` for everything else,** especially conversations between other users that the bot is not a part of.

## Conversation Context
```
{conversation_history}
```

## Analysis Task
Analyze the conversation above. Should the bot '{bot_name}' respond to the very last message? Provide your decision in the required JSON format.

## Example of YOUR REQUIRED FINAL OUTPUT
```json
{{"should_respond": true}}
```
"""

## MODIFIÉ : Le prompt du répartiteur est enrichi pour mieux guider le LLM.
DISPATCHER_SYSTEM_PROMPT = """## Your Role: Tool Dispatcher
You are a specialized AI model acting as a tool dispatcher. Your SOLE PURPOSE is to analyze the user's message and decide if one or more of the available tools MUST be called to answer it. You do not, under any circumstances, generate a conversational reply. You must understand requests in different languages (like French) and map them to the correct tool.

## Critical Rules
1.  **Your ONLY output MUST be a single, valid JSON object.**
2.  **Tool Priority:** Tools are the absolute source of truth. If the user's request can be fulfilled by a tool, you MUST call it. Your internal knowledge is irrelevant for this task.
3.  **If a tool is needed:** Your JSON output MUST contain the key "tool_calls" with a list of the required tool calls.
4.  **If NO tool is needed:** Your JSON output MUST contain the key "tool_calls" with the value `null`.
5.  **ABSOLUTE PROHIBITION:** Do not output any text, explanation, or conversational filler. Your entire response must be ONLY the JSON object.

## Tool Capabilities Guide
- **Image Generation:** If the user asks to 'draw', 'create an image', 'generate a picture', 'dessiner', 'créer une image', 'génère une image', etc., you MUST use the appropriate image generation tool.
- **Time Information:** If the user asks for the current time, date, or day, you MUST use the time tool.
- **User Information:** If the user asks for information about a specific person in the chat, you MUST use the user information tool.

## Examples

User: "hey, how are you?"
Your REQUIRED output:
```json
{"tool_calls": null}
```

User: "what time is it please?"
Your REQUIRED output (assuming `get_current_time` tool exists):
```json
{"tool_calls": [{"function": {"name": "get_current_time", "arguments": {}}}]}
```

User: "dessine-moi un chat avec un chapeau"
Your REQUIRED output (assuming `generate_image` tool exists):
```json
{"tool_calls": [{"function": {"name": "generate_image", "arguments": {"prompt": "a cat wearing a hat"}}}]}
```

User: "what time is it, and could you also look up info on the user Holaf?"
Your REQUIRED output:
```json
{
    "tool_calls": [
    {
        "function": {
        "name": "get_current_time",
        "arguments": {}
        }
    },
    {
        "function": {
        "name": "get_user_info",
        "arguments": {
            "user_identifier": "Holaf"
        }
        }
    }
    ]
}
```
"""

SYNTHESIZER_SYSTEM_PROMPT = """## Core Directives & Rules
1.  **You are a helpful AI assistant operating within the Discord chat platform.** All interactions happen inside this context.
2.  **CRITICAL RULE: Information from tools, which appears in the conversation history with the role 'tool', is the absolute source of truth.** It overrides your internal knowledge. You MUST use this information to formulate your answer without expressing surprise or doubt.
3.  **You are in a multi-user channel. Pay strict attention to the [user:NAME] prefixes in the conversation history.** Each name represents a unique individual. You MUST track the context for each user separately and address them by their name when appropriate to avoid confusion.
4.  **Your primary role is to synthesize all the information provided (user query, conversation history, tool results) into a clear, helpful, and natural-sounding conversational response.**
5.  **CONDITIONAL RULE: If your response immediately follows a message with `role: tool`, you MUST start by directly addressing the user who initiated the request.**
"""

ACKNOWLEDGE_SYSTEM_PROMPT = """## Your Role: AI Acknowledgement Specialist
You are a specialized AI model. Your SOLE task is to generate a very short, friendly, and non-committal acknowledgement message. This message informs the user that their request has been understood and is being processed, especially when it involves a slow task.

## Your Persona
- You are '{bot_name}'.
- You are speaking to '{user_display_name}'.
- The task you are starting is related to: '{tool_name}'.

## Critical Rules
1.  **Be Brief:** Your message should be a single, short sentence.
2.  **Be Conversational:** Use a friendly and natural tone.
3.  **DO NOT mention the tool name.** Simply allude to the task. For example, if the tool is `generate_image`, you might say "Let me get my pencils out..." or "Working on that picture for you!".
4.  **DO NOT promise a specific outcome or delivery time.**
5.  **Your entire output MUST be only the text of the message, and nothing else.**

## Example Scenarios
- If tool_name is 'generate_image': "One moment, I'm working on that image for you."
- If tool_name is 'research_topic': "Okay, let me look into that for you."
- If tool_name is 'summarize_document': "Sure, I'll start summarizing that document now."

## Your Task
Generate the acknowledgement message now.
"""

ARCHIVIST_SYSTEM_PROMPT = """## Your Role: Archivist AI
You are a specialized AI model that acts as an archivist. Your SOLE PURPOSE is to analyze the final turn of a conversation (a user's message and the bot's response) and decide if a new, single, factual note about the USER who sent the message should be permanently saved.

## Critical Rules
1.  **Your ONLY output MUST be a single, valid JSON object.**
2.  **Focus on Facts:** You only save objective, factual information about the user. Do not save opinions, feelings, or transient information (e.g., "user is happy right now").
3.  **Target User:** The note MUST be about the user who sent the message. Use 'User' as the identifier.
4.  **If a note should be saved:** Your JSON output MUST contain the key "tool_calls" with a list containing a single `save_user_note` tool call.
5.  **If NO note is needed:** Your JSON output MUST contain the key "tool_calls" with the value `null`.
6.  **ABSOLUTE PROHIBITION:** Do not output any text, explanation, or conversational filler. Your entire response must be ONLY the JSON object.

## Examples

Conversation Turn:
User (Grolaf): "My favorite color is blue."
Bot: "Got it, blue is a great color!"
Your REQUIRED output:
```json
{"tool_calls": [{"function": {"name": "save_user_note", "arguments": {"user_identifier": "User", "note": "User's favorite color is blue.", "reliability_score": 95}}}]}
```

Conversation Turn:
User (Grolaf): "Can you tell me the time?"
Bot: "It is currently 4:30 PM."
Your REQUIRED output:
```json
{"tool_calls": null}
```

Conversation Turn:
User (Grolaf): "I work as a software developer."
Bot: "That's interesting! I enjoy working with code."
Your REQUIRED output:
```json
{"tool_calls": [{"function": {"name": "save_user_note", "arguments": {"user_identifier": "User", "note": "User is a software developer.", "reliability_score": 95}}}]}
```
"""

ARCHIVIST_TOOL_DEFINITION = [
    {
        "type": "function",
        "function": {
            "name": "save_user_note",
            "description": "Saves a single factual note about a user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_identifier": {
                        "type": "string",
                        "description": "The identifier for the user. ALWAYS use the literal string 'User'."
                    },
                    "note": {
                        "type": "string",
                        "description": "The text of the note to be saved. Must be a single, concise fact."
                    },
                    "reliability_score": {
                        "type": "integer",
                        "description": "An integer from 0 to 100 representing confidence in the note's accuracy. E.g., 95 if the user stated it themselves."
                    }
                },
                "required": ["user_identifier", "note", "reliability_score"]
            }
        }
    }
]


# --- MCP Client Logic ---
JSONRPC_ID_COUNTER = itertools.count(1)

async def mcp_request(url: str, method: str, params: Dict | None = None) -> Dict:
    payload = {"jsonrpc": "2.0", "method": method, "id": next(JSONRPC_ID_COUNTER)}
    if params:
        payload["params"] = params

    async with httpx.AsyncClient() as client:
        headers = {'Content-Type': 'application/json'}
        response = await client.post(url, content=json.dumps(payload), headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()

async def discover_mcp_tools(mcp_servers_list) -> List[Dict]:
    if not mcp_servers_list:
        return []
    logging.info("Starting MCP tool discovery...")
    all_tool_definitions = []
    for server in mcp_servers_list:
        if not server.enabled:
            continue
        # MODIFIÉ : Utilise le chemin de l'endpoint dynamique de la BDD au lieu d'une valeur codée en dur.
        server_url = f"http://{server.host}:{server.port}{server.rpc_endpoint_path}"
        try:
            rpc_response = await mcp_request(server_url, "tools/list")
            if "result" in rpc_response and "tools" in rpc_response["result"]:
                server_tools = rpc_response["result"]["tools"]
                all_tool_definitions.extend(server_tools)
                logging.info(f"Successfully discovered {len(server_tools)} tools from {server_url}")
        except Exception as e:
            logging.error(f"Could not discover tools from {server_url}. Error: {e}")
    logging.info(f"MCP tool discovery finished. Total tools found: {len(all_tool_definitions)}")
    return all_tool_definitions

def _convert_mcp_tools_to_ollama_format(mcp_tools: List[Dict]) -> List[Dict]:
    if not mcp_tools:
        return []
    return [{
        "type": "function",
        "function": {
            "name": tool.get("name"),
            "description": tool.get("description"),
            "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
        }
    } for tool in mcp_tools]

def _normalize_dispatcher_response(decision: Dict) -> Dict:
    """
    Ensures the dispatcher's response adheres to the expected format.
    The LLM sometimes returns a 'flat' object for a single tool call.
    This function wraps it in the standard `{"tool_calls": [...]}` structure.
    """
    if "tool_calls" in decision:
        # The response is already in the correct format or is a valid `{"tool_calls": null}`.
        return decision

    # Check for the known 'flat' format: `{"name": "...", "arguments": {...}}`
    if isinstance(decision.get("name"), str) and isinstance(decision.get("arguments"), dict):
        logging.info(f"Normalizing a 'flat' tool call response from LLM: {decision}")
        return {
            "tool_calls": [{
                "function": {
                    "name": decision["name"],
                    "arguments": decision["arguments"]
                }
            }]
        }
    
    # Fallback for any other unexpected format.
    logging.warning(f"Dispatcher LLM returned an unrecognized format: {decision}. Defaulting to no tool call.")
    return {"tool_calls": None}

# MODIFIED: Use Union to accept both ChatRequest and SynthesizeRequest
async def _build_common_context(request: Union[chat_schemas.ChatRequest, chat_schemas.SynthesizeRequest], db: Session, bot: Any) -> Tuple[str, str, str]:
    """Helper to build context strings used by both Dispatcher and Synthesizer."""
    last_user_message = next((msg.content for msg in reversed(request.messages) if msg.role == 'user'), None)

    # Location Context
    location_context_info = ""
    if request.channel_context:
        if request.channel_context.context_type == "SERVER_CHANNEL":
            location_context_info = (f"## Current Location\n- Discord Server: {request.channel_context.server_name}\n- Discord Channel: #{request.channel_context.channel_name}\n\n")
        elif request.channel_context.context_type == "DIRECT_MESSAGE" and request.user_context:
            location_context_info = (f"## Current Location\n- You are in a Direct Message with the user '{request.user_context.display_name}'.\n\n")

    # Attached Files Context
    attached_files_info = ""
    if request.attached_files:
        file_lines = [f"- '{f.filename}' (UUID: {f.uuid}, Type: {f.file_family})" for f in request.attached_files]
        file_list_str = "\n".join(file_lines)
        attached_files_info = (f"System Information: The user has just uploaded the following files. You can use tools to interact with them.\n{file_list_str}\n\n")
        logging.info(f'Injecting file info into system prompt: {attached_files_info.strip()}')

    # LTM Context
    context_from_memory = ""
    bot_collection = chroma_manager.get_or_create_bot_collection(bot_id=bot.id)
    if bot_collection and last_user_message:
        try:
            results = bot_collection.query(query_texts=[last_user_message], n_results=MEMORY_DEPTH)
            if results and results.get('documents') and results['documents']:
                retrieved_docs = results['documents'][0] # Chroma returns a list of lists
                retrieved_docs.reverse()
                formatted_history = "\n".join(retrieved_docs)
                context_from_memory = f"Here are relevant excerpts from our previous conversation to give you context:\n---\n{formatted_history}\n---\n\n"
        except Exception as e:
            logging.warning(f"ChromaDB query failed for bot {bot.id}: {e}")

    return location_context_info, attached_files_info, context_from_memory

# --- New Gatekeeper Logic ---
async def get_gatekeeper_decision(request: chat_schemas.ChatRequest, db: Session) -> Dict:
    bot_id = request.bot_id
    logging.info(f"Gatekeeper invoked for bot_id={bot_id}.")

    client = OllamaClient()

    try:
        bot = crud_bots.get_bot(db, bot_id=bot_id)
        if not bot:
            return {"error": f"Bot with ID {bot_id} not found."}

        global_settings = crud_settings.get_global_settings(db)
        model_name = bot.llm_model or global_settings.default_llm_model

        if not model_name:
            return {"error": "No LLM model configured."}

        # *** MODIFICATION START ***
        # Correctly assemble the full conversation context from both history and the current message.
        past_history = request.channel_history or []
        current_message_content = [msg.content for msg in request.messages if msg.role == 'user']
        full_context = past_history + current_message_content
        conversation_history_str = "\n".join(full_context)
        # *** MODIFICATION END ***

        gatekeeper_prompt = GATEKEEPER_SYSTEM_PROMPT.format(
            bot_name=bot.name, 
            conversation_history=conversation_history_str
        )
        
        messages_for_llm = [
            {"role": "system", "content": gatekeeper_prompt}
        ]
        
        response = await client.chat_response(
            model=model_name,
            messages=messages_for_llm,
            format="json",
        )

        response_content = response.get("message", {}).get("content", "{}")
        decision = json.loads(response_content)

        logging.info(f"Gatekeeper decision: {decision}")
        return decision

    except json.JSONDecodeError as e:
        logging.error(f"Gatekeeper failed to decode JSON response from LLM: {e}. Response was: {response_content}")
        return {"error": "Gatekeeper received an invalid JSON response from the LLM."}
    except Exception as e:
        logging.error(f"Critical gatekeeper error: {e}", exc_info=True)
        return {"error": f"Gatekeeper error: {e}"}


# --- New Dispatcher Logic ---
async def get_dispatch_decision(request: chat_schemas.ChatRequest, db: Session) -> Dict:
    bot_id = request.bot_id
    logging.info(f"Dispatcher invoked for bot_id={bot_id}.")

    client = OllamaClient()

    try:
        bot = crud_bots.get_bot(db, bot_id=bot_id)
        if not bot:
            return {"error": f"Bot with ID {bot_id} not found."}

        global_settings = crud_settings.get_global_settings(db)
        model_name = bot.llm_model or global_settings.default_llm_model

        if not model_name:
            return {"error": "No LLM model configured."}

        location_context, files_context, memory_context = await _build_common_context(request, db, bot)
        bot_personality_prompt = request.system or bot.system_prompt or ""
        final_system_prompt = (f"{DISPATCHER_SYSTEM_PROMPT}\n\n{location_context}{files_context}{memory_context}{bot_personality_prompt}")

        discovered_mcp_tools = await discover_mcp_tools(bot.mcp_servers or [])
        ollama_formatted_mcp_tools = _convert_mcp_tools_to_ollama_format(discovered_mcp_tools)
        internal_tools = request.tools or []
        combined_tools = internal_tools + ollama_formatted_mcp_tools
        logging.info(f"Dispatcher tools for LLM: {len(combined_tools)} total.")

        messages_for_llm = [
            {"role": "system", "content": final_system_prompt}
        ]
        messages_for_llm.extend([msg.model_dump(exclude_none=True) for msg in request.messages])

        response = await client.chat_response(
            model=model_name,
            messages=messages_for_llm,
            tools=combined_tools,
            format="json",
        )

        response_content = response.get("message", {}).get("content", "{}")
        tool_call_decision = json.loads(response_content)

        normalized_decision = _normalize_dispatcher_response(tool_call_decision)

        logging.info(f"Dispatcher raw decision: {tool_call_decision}")
        logging.info(f"Dispatcher normalized decision: {normalized_decision}")
        return normalized_decision

    except json.JSONDecodeError as e:
        logging.error(f"Dispatcher failed to decode JSON response from LLM: {e}. Response was: {response_content}")
        return {"error": "Dispatcher received an invalid JSON response from the LLM."}
    except Exception as e:
        logging.error(f"Critical dispatcher error: {e}", exc_info=True)
        return {"error": f"Dispatcher error: {e}"}

# --- Refactored Synthesizer Logic ---
# MODIFIED: Use the new tool-less SynthesizeRequest schema
async def get_synthesized_response_stream(request: chat_schemas.SynthesizeRequest, db: Session) -> AsyncIterator[str]:
    bot_id = request.bot_id
    last_user_message = next((msg.content for msg in reversed(request.messages) if msg.role == 'user'), None)
    logging.info(f"Synthesizer invoked for bot_id={bot_id}.")

    client = OllamaClient()

    try:
        bot = crud_bots.get_bot(db, bot_id=bot_id)
        if not bot:
            yield json.dumps({"error": f"Bot with ID {bot_id} not found."}) + '\n'
            return

        global_settings = crud_settings.get_global_settings(db)
        model_name = bot.llm_model or global_settings.default_llm_model

        if not model_name:
            yield json.dumps({"error": "No LLM model configured."}) + '\n'
            return

        location_context, files_context, memory_context = await _build_common_context(request, db, bot)

        bot_personality_prompt = request.system or bot.system_prompt or ""
        final_system_prompt = (f"{SYNTHESIZER_SYSTEM_PROMPT}\n\n{location_context}{files_context}{memory_context}{bot_personality_prompt}")
        logging.info("Constructed final synthesizer system prompt.")

        messages_for_llm = [
            {"role": "system", "content": final_system_prompt}
        ]
        messages_for_llm.extend([msg.model_dump(exclude_none=True) for msg in request.messages])

        # CRITICAL: Tools are explicitly an empty list, preventing the Synthesizer from calling any.
        stream = client.chat_streaming_response(
            model=model_name,
            messages=messages_for_llm,
            tools=[]
        )

        final_text_response = ""

        async for line in stream:
            yield line.strip() + '\n'
            if line.strip():
                try:
                    data = json.loads(line)
                    chunk = data.get('message', {}).get('content', '')
                    if chunk:
                        final_text_response += chunk
                except json.JSONDecodeError:
                    logging.warning(f"Failed to decode JSON from stream line: {line}")
                    continue

        # --- Post-Stream: Save to LTM ---
        bot_collection = chroma_manager.get_or_create_bot_collection(bot_id=bot.id)
        if bot_collection and last_user_message and final_text_response.strip():
            logging.info("Final text response detected, saving exchange to LTM.")
            try:
                # ADDED: Clean the response to remove the <think> block before saving to LTM.
                cleaned_response_for_ltm = re.sub(r'<think>.*?</think>', '', final_text_response, flags=re.DOTALL).strip()

                exchange_document = f"{request.user_context.display_name or 'User'}: {last_user_message}\nBot: {cleaned_response_for_ltm}" # MODIFIED: Use cleaned response

                raw_metadata = { "timestamp_utc": datetime.now(timezone.utc).isoformat() }
                if request.user_context:
                    raw_metadata.update({
                        "user_id": str(request.user_context.discord_id),
                        "user_name": request.user_context.name,
                        "user_display_name": request.user_context.display_name
                    })
                if request.channel_context:
                    raw_metadata.update({
                        "context_type": request.channel_context.context_type,
                        "server_id": str(request.channel_context.server_id) if request.channel_context.server_id else None,
                        "server_name": request.channel_context.server_name,
                        "channel_id": str(request.channel_context.channel_id) if request.channel_context.channel_id else None,
                        "channel_name": request.channel_context.channel_name
                    })

                memory_metadata = {k: v for k, v in raw_metadata.items() if v is not None}

                if cleaned_response_for_ltm: # Ensure we don't save an empty bot response
                    bot_collection.add(documents=[exchange_document], metadatas=[memory_metadata], ids=[str(uuid.uuid4())])
            except Exception as e:
                logging.error(f"ChromaDB save FAILED for bot {bot.id}. Error: {e}", exc_info=True)
        else:
            logging.info("No final text response or user message, skipping LTM save.")

    except Exception as e:
        logging.error(f"Critical synthesizer error: {e}", exc_info=True)
        error_payload = {"error": f"Synthesizer error: {e}", "traceback": traceback.format_exc()}
        yield json.dumps(error_payload) + '\n'

# --- New Acknowledge-Synthesizer Logic ---
async def generate_acknowledgement_message(request: chat_schemas.AcknowledgeRequest, db: Session) -> str:
    """
    Generates a short, conversational message to inform the user that a slow tool is being executed.
    """
    bot_id = request.bot_id
    logging.info(f"Acknowledge-Synthesizer invoked for bot_id={bot_id} for tool '{request.tool_name}'.")

    client = OllamaClient()

    try:
        bot = crud_bots.get_bot(db, bot_id=bot_id)
        if not bot:
            raise ValueError(f"Bot with ID {bot_id} not found.")

        global_settings = crud_settings.get_global_settings(db)
        model_name = bot.llm_model or global_settings.default_llm_model
        if not model_name:
            raise ValueError("No LLM model configured.")

        # --- MODIFICATION START ---
        # Combine the bot's main system prompt with the specific acknowledgement instructions.
        bot_personality = bot.system_prompt or ""
        
        ack_instructions = ACKNOWLEDGE_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            user_display_name=request.user_context.display_name,
            tool_name=request.tool_name
        )

        final_prompt = f"{bot_personality}\n\n{ack_instructions}"
        
        messages_for_llm = [{"role": "system", "content": final_prompt}]
        # --- MODIFICATION END ---
        
        response = await client.chat_response(
            model=model_name,
            messages=messages_for_llm
        )

        message_content = response.get("message", {}).get("content", "One moment...").strip()
        message_content = message_content.strip('"') # Sanitize response

        logging.info(f"Acknowledge-Synthesizer generated message: '{message_content}'")
        return message_content

    except Exception as e:
        logging.error(f"Critical Acknowledge-Synthesizer error: {e}", exc_info=True)
        return "Got it, I'm working on your request." # Fallback message

# --- New Archivist Logic ---
async def run_archivist(db: Session, request: chat_schemas.ChatRequest, final_response: str):
    """
    Analyzes the conversation turn and saves a user note if necessary.
    This runs asynchronously and does not return a response to the user.
    """
    logging.info(f"Archivist invoked for bot_id={request.bot_id}.")

    if not request.user_context or not request.channel_context or not request.channel_context.server_id:
        logging.warning("Archivist skipped: Missing user or server context for potential note saving.")
        return

    last_user_message = next((msg.content for msg in reversed(request.messages) if msg.role == 'user'), None)
    if not last_user_message or not final_response.strip():
        logging.info("Archivist skipped: No user message or final bot response found.")
        return

    client = OllamaClient()
    try:
        bot = crud_bots.get_bot(db, bot_id=request.bot_id)
        if not bot:
            logging.error(f"Archivist error: Bot with ID {request.bot_id} not found.")
            return

        global_settings = crud_settings.get_global_settings(db)
        model_name = bot.llm_model or global_settings.default_llm_model
        if not model_name:
            logging.error("Archivist error: No LLM model configured.")
            return

        # The context for the archivist is just the last exchange
        conversation_turn = f"User ({request.user_context.display_name}): {last_user_message}\nBot: {final_response.strip()}"
        messages_for_llm = [
            {"role": "system", "content": ARCHIVIST_SYSTEM_PROMPT},
            {"role": "user", "content": conversation_turn}
        ]

        response = await client.chat_response(
            model=model_name,
            messages=messages_for_llm,
            tools=ARCHIVIST_TOOL_DEFINITION,
            format="json",
        )

        response_content = response.get("message", {}).get("content", "{}")
        decision = json.loads(response_content)

        tool_calls = decision.get("tool_calls")
        if not tool_calls:
            logging.info("Archivist decision: No note to save.")
            return

        # Process the first valid tool call to save a note
        for call in tool_calls:
            if call.get("function", {}).get("name") == "save_user_note":
                args = call.get("function", {}).get("arguments", {})
                note_content = args.get("note")
                reliability_score = args.get("reliability_score")

                if not note_content or reliability_score is None:
                    logging.warning(f"Archivist: Skipping invalid tool call with missing arguments: {args}")
                    continue

                note_schema = UserNoteCreate(
                    bot_id=request.bot_id, # *** CORRECTION ICI ***
                    user_discord_id=request.user_context.discord_id,
                    server_discord_id=request.channel_context.server_id,
                    author_discord_id=request.user_context.discord_id, # The user is the author of their own facts
                    note_content=note_content,
                    reliability_score=reliability_score
                )

                crud_user_notes.create_user_note(db=db, note=note_schema)
                logging.info(f"Archivist successfully saved note for user {request.user_context.discord_id} on server {request.channel_context.server_id}.")
                # We only process the first valid call
                break

    except json.JSONDecodeError as e:
        logging.error(f"Archivist failed to decode JSON response from LLM: {e}. Response was: {response_content}")
    except Exception as e:
        logging.error(f"Critical archivist error: {e}", exc_info=True)