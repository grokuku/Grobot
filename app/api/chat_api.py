# /app/app/api/chat_api.py
import logging
import json
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import redis

from app.core import agent_orchestrator
from app.core.agents import archivist, synthesizer
from app.database import crud_bots, crud_user_notes, crud_user_profiles, sql_session, crud_settings
from app.database import redis_session
from app.schemas import chat_schemas

logger = logging.getLogger(__name__)
router = APIRouter()

CHAT_CONTEXT_EXPIRATION_S = 600


@router.post(
    "/process_message",
    response_model=Union[
        chat_schemas.StopResponse,
        chat_schemas.ClarifyResponse,
        chat_schemas.AcknowledgeAndExecuteResponse,
        chat_schemas.SynthesizeResponse
    ],
    summary="Process a user message through the agent chain"
)
async def process_message(
    request: chat_schemas.ProcessMessageRequest,
    db: Session = Depends(sql_session.get_db),
    redis_client: redis.Redis = Depends(redis_session.get_redis)
):
    """
    Main endpoint for processing all user messages.
    It now saves the execution context, including the plan, to Redis.
    """
    try:
        action = await agent_orchestrator.process_user_message(db=db, request=request)

        if isinstance(action, chat_schemas.AcknowledgeAndExecuteResponse):
            context_to_save = {
                "bot_id": request.bot_id,
                "history": [msg.model_dump() for msg in request.history],
                "plan": action.plan.model_dump() if action.plan else None,
                "tool_definitions": action.tool_definitions if action.tool_definitions else []
            }
            redis_client.set(
                f"chat_context:{request.message_id}", 
                json.dumps(context_to_save), 
                ex=CHAT_CONTEXT_EXPIRATION_S
            )
        elif isinstance(action, chat_schemas.SynthesizeResponse):
            context_to_save = {
                "bot_id": request.bot_id,
                "history": [msg.model_dump() for msg in request.history],
                "plan": None,
                "tool_definitions": []
            }
            redis_client.set(
                f"chat_context:{request.message_id}",
                json.dumps(context_to_save),
                ex=CHAT_CONTEXT_EXPIRATION_S
            )
        
        return action
    except Exception as e:
        logger.critical(f"A critical error occurred in the agent orchestrator: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An internal error occurred in the agent orchestrator.")


@router.get("/stream/{message_id}", summary="Execute plan and stream the final response")
async def stream_response(
    message_id: str,
    request: Request,
    db: Session = Depends(sql_session.get_db),
    redis_client: redis.Redis = Depends(redis_session.get_redis)
):
    """
    This endpoint now retrieves a pre-computed plan from Redis, executes it,
    and streams the final synthesized response.
    """
    context_key = f"chat_context:{message_id}"
    context_data = redis_client.get(context_key)
    if not context_data:
        raise HTTPException(status_code=404, detail="Chat session expired or not found.")
    
    context = json.loads(context_data)
    bot_id = context.get("bot_id")
    history_data = context.get("history", [])
    plan_data = context.get("plan")
    tool_definitions = context.get("tool_definitions", [])

    bot = crud_bots.get_bot(db=db, bot_id=bot_id)
    if not bot:
            raise HTTPException(status_code=404, detail=f"Bot with id {bot_id} not found.")
    
    global_settings = crud_settings.get_global_settings(db)

    tool_results = []
    if plan_data and tool_definitions:
        plan_result = chat_schemas.PlannerResult.model_validate(plan_data)
        logger.info(f"Executing pre-computed plan for message {message_id}")
        tool_results = await agent_orchestrator.execute_tool_plan(
            db=db, bot_id=bot_id, plan_result=plan_result, tool_definitions=tool_definitions
        )
        logger.info(f"Plan execution finished. Results: {tool_results}")
    else:
        logger.info(f"No execution plan found for message {message_id}, proceeding directly to synthesizer.")

    async def event_generator():
        try:
            logger.info(f"Starting synthesis phase for message {message_id}")
            
            # MODIFICATION: Use the new synthesis phase router instead of a direct call.
            async for chunk in agent_orchestrator.run_synthesis_phase(
                bot=bot,
                global_settings=global_settings,
                history=history_data,
                tool_results=tool_results
            ):
                if await request.is_disconnected():
                    logger.warning("Client disconnected, stopping stream.")
                    break
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            
            logger.info(f"Synthesis stream finished for message {message_id}")

        except Exception as e:
            logger.error(f"Error during streaming for message {message_id}: {e}", exc_info=True)
            error_message = json.dumps({"error": "An error occurred while generating the response."})
            yield f"data: {error_message}\n\n"
        finally:
            logger.info(f"Cleaning up Redis context for message_id: {message_id}")
            redis_client.delete(context_key)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/archive", status_code=202, summary="Archive a conversation")
async def archive_conversation(
    request: chat_schemas.ArchiveRequest,
    db: Session = Depends(sql_session.get_db)
):
    """
    Analyzes a conversation and saves key facts to the user's long-term memory.
    """
    logger.info(f"Archivist received conversation for user {request.user_display_name}")
    try:
        # MODIFIED: Fetch bot and global settings to pass to the archivist
        bot = crud_bots.get_bot(db, request.bot_id)
        if not bot:
            logger.error(f"Archivist: Bot with ID {request.bot_id} not found.")
            # We still return a 202 to not block the client, but log the error
            return {"message": "Accepted, but bot not found."}

        global_settings = crud_settings.get_global_settings(db)

        archivist_decision = await archivist.run_archivist(
            bot=bot,
            global_settings=global_settings,
            full_conversation=request.conversation_history
        )

        if not archivist_decision.notes_to_create:
            logger.info("Archivist found nothing to save.")
            return {"message": "Accepted. No notes to create."}

        user_id_str = str(request.user_id)
        user_profile = crud_user_profiles.get_or_create_profile(
            db, bot_id=request.bot_id, user_id=user_id_str, display_name=request.user_display_name, username=request.user_name
        )

        for note in archivist_decision.notes_to_create:
            crud_user_notes.create_user_note(
                db,
                user_profile_id=user_profile.id,
                author_id=user_id_str,
                fact=note.fact,
                reliability_score=note.reliability_score
            )
        
        logger.info(f"Successfully created {len(archivist_decision.notes_to_create)} notes for user {request.user_display_name}")
        return {"message": f"Accepted. Created {len(archivist_decision.notes_to_create)} notes."}

    except Exception as e:
        logger.error(f"An error occurred during conversation archiving: {e}", exc_info=True)
        return {"message": "Accepted, but an internal error occurred during processing."}