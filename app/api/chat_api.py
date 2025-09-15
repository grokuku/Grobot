# app/api/chat_api.py
import json
import traceback
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core import agent_logic
from app.schemas import chat_schemas, bot_schemas
from app.database.sql_session import get_db
from app.database.chroma_manager import chroma_manager
from app.worker.tasks import run_archivist_task
# --- NOUVELLES IMPORTATIONS ---
from app.api.tools_api import execute_tool_call
from app.api.tools_api import ToolCallRequest as ApiToolCallRequest

router = APIRouter(
    prefix="/chat",
    tags=["Chat & Memory"],
)

async def stream_error_wrapper(generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    """
    Wraps a generator to catch any exception that occurs during its execution.
    If an error occurs, it yields a single JSON object with the error details.
    """
    try:
        async for item in generator:
            yield item
    except Exception as e:
        error_payload = {
            "error": f"An unexpected error occurred in the agent logic: {e}",
            "traceback": traceback.format_exc()
        }
        # Yield a JSON string with a newline to ensure it's a complete line
        yield json.dumps(error_payload) + '\n'


@router.post("/gatekeeper")
async def handle_chat_gatekeeper(
    request: chat_schemas.ChatRequest,
    db: Session = Depends(get_db)
):
    """
    [Phase 0: Gatekeeper]
    Analyzes the user's request and conversation history to decide if the bot should respond at all.
    Returns a JSON object with the decision. This is a non-streaming, lightweight endpoint.
    """
    try:
        decision = await agent_logic.get_gatekeeper_decision(request, db)
        if "error" in decision:
            raise HTTPException(status_code=500, detail=decision["error"])
        return JSONResponse(content=decision)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process gatekeeper request: {e}")


@router.post("/dispatch")
async def handle_chat_dispatch(
    request: chat_schemas.ChatRequest,
    db: Session = Depends(get_db)
):
    """
    [Phase 1: Dispatcher]
    Analyzes the user's request and conversation history to decide if a tool should be called.
    Returns a JSON object with the tool call decision. This is a non-streaming endpoint.
    """
    try:
        decision = await agent_logic.get_dispatch_decision(request, db)
        if "error" in decision:
            raise HTTPException(status_code=500, detail=decision["error"])
        return JSONResponse(content=decision)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process dispatch request: {e}")


@router.post("/")
async def handle_chat_synthesis_stream(
    request: chat_schemas.SynthesizeRequest, # MODIFIED: Use the new tool-less schema
    db: Session = Depends(get_db)
):
    """
    [Phase 2: Synthesizer]
    Handles a stateful, streaming chat request. It expects a full message history
    (which may include tool call results) and streams a final conversational response.
    """
    # The generator is created here, but not yet executed.
    response_generator = agent_logic.get_synthesized_response_stream(request, db)
    # The wrapper will handle exceptions during execution.
    safe_generator = stream_error_wrapper(response_generator)
    return StreamingResponse(safe_generator, media_type="application/x-ndjson")


@router.post("/acknowledge", response_model=chat_schemas.AcknowledgeResponse)
async def handle_acknowledgement_synthesis(
    request: chat_schemas.AcknowledgeRequest,
    db: Session = Depends(get_db)
):
    """
    [Phase 1.5: Acknowledge-Synthesizer]
    Generates a short acknowledgement message when a slow tool is about to be run.
    This is a non-streaming endpoint.
    """
    try:
        message = await agent_logic.generate_acknowledgement_message(request, db)
        return chat_schemas.AcknowledgeResponse(acknowledgement_message=message)
    except Exception as e:
        # We must not fail the entire flow. Return a fallback response.
        return chat_schemas.AcknowledgeResponse(acknowledgement_message="Working on it...")


@router.post("/archive", status_code=status.HTTP_202_ACCEPTED)
async def handle_archivist_request(
    request: chat_schemas.ArchivistRequest
):
    """
    [Phase 3: Archivist]
    Receives the context of a completed conversation turn and queues an asynchronous
    task for the Archivist to decide if a user note should be saved.
    """
    try:
        # Sérialise la requête de chat en JSON pour le passage à Celery
        chat_context_json = request.chat_context.model_dump_json()

        # Lance la tâche Celery en arrière-plan
        run_archivist_task.delay(
            chat_request_json=chat_context_json,
            final_response=request.final_bot_response
        )
        return {"status": "Archivist task accepted"}
    except Exception as e:
        # Note: Celery's .delay() can raise exceptions if the broker is down.
        raise HTTPException(status_code=503, detail=f"Failed to queue archivist task: {e}")


# --- MODIFICATION MAJEURE : L'ENDPOINT DE TEST SIMULE MAINTENANT LA CHAÎNE COMPLÈTE ---
@router.post("/test", response_model=chat_schemas.TestChatResponse)
async def handle_test_chat(
    request: chat_schemas.TestChatRequest,
    db: Session = Depends(get_db)
):
    """
    Handles a stateless chat request from the UI test tool by simulating the full agent chain.
    This endpoint now supports tool usage.
    """
    try:
        # 1. Forger un contexte de requête complet pour simuler un vrai message Discord.
        fake_user_context = chat_schemas.UserContext(discord_id=1000, name="testuser", display_name="Test User")
        fake_channel_context = chat_schemas.ChannelContext(context_type="DIRECT_MESSAGE", server_id=None, server_name=None, channel_id=2000, channel_name="Test DM")
        
        messages = [chat_schemas.ChatMessage(role="user", content=request.user_message)]

        dispatch_request = chat_schemas.ChatRequest(
            bot_id=request.bot_id,
            messages=messages,
            user_context=fake_user_context,
            channel_context=fake_channel_context,
            channel_history=None, system=None, tools=None, attached_files=None
        )

        # 2. Appeler le Répartiteur (Dispatcher) pour voir si un outil est nécessaire.
        dispatch_decision = await agent_logic.get_dispatch_decision(dispatch_request, db)
        if "error" in dispatch_decision:
            raise HTTPException(status_code=500, detail=f"Dispatcher error in test chat: {dispatch_decision['error']}")

        tool_calls = dispatch_decision.get("tool_calls")

        # 3. Exécuter les outils si le Répartiteur en a demandé.
        if tool_calls:
            messages.append(chat_schemas.ChatMessage(role="assistant", content="", tool_calls=tool_calls))

            for tool_call in tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")
                arguments = function_call.get("arguments", {})

                if not tool_name: continue

                tool_request = ApiToolCallRequest(bot_id=request.bot_id, tool_name=tool_name, arguments=arguments)
                tool_result_dict = await execute_tool_call(tool_request, db)
                
                tool_content_list = tool_result_dict.get("content", [])
                tool_result_text = "\n".join([item.get("text", "") for item in tool_content_list if item.get("type") == "text"])

                messages.append(chat_schemas.ChatMessage(role="tool", content=tool_result_text))

        # 4. Appeler le Synthétiseur avec l'historique final (qui peut inclure les résultats des outils).
        synthesis_request = chat_schemas.SynthesizeRequest(
            bot_id=request.bot_id,
            messages=messages,
            user_context=fake_user_context,
            channel_context=fake_channel_context,
            channel_history=None, system=None, attached_files=None
        )
        
        full_response = ""
        async for line in agent_logic.get_synthesized_response_stream(synthesis_request, db):
            if line.strip():
                try:
                    data = json.loads(line)
                    if 'error' in data:
                        return chat_schemas.TestChatResponse(bot_response=f"ERROR: {data['error']}")
                    if data.get('message', {}).get('content'):
                        full_response += data['message']['content']
                except json.JSONDecodeError:
                    continue

        return chat_schemas.TestChatResponse(bot_response=full_response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process test chat: {str(e)}")

@router.get("/memory/{bot_id}", response_model=bot_schemas.BotMemory)
def get_bot_memory(bot_id: int):
    """
    Retrieves all memory entries for a specific bot from ChromaDB.
    """
    memory_data = chroma_manager.get_bot_memory(bot_id)
    if memory_data is None:
        raise HTTPException(status_code=404, detail=f"Could not retrieve memory for Bot ID {bot_id}. The collection may not exist or an error occurred.")
    return memory_data

@router.delete("/memory/{bot_id}/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bot_memory_entry(bot_id: int, memory_id: str):
    """
    Deletes a specific memory entry for a bot.
    """
    success = chroma_manager.delete_memory_entry(bot_id=bot_id, memory_id=memory_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Memory entry with ID '{memory_id}' not found for bot {bot_id}, or an error occurred during deletion.")
    # On success, return a 204 No Content response, as is standard for DELETE operations.
    return