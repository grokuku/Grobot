# app/worker/tasks.py
import logging
import asyncio
from celery import shared_task
from sqlalchemy.orm import Session
import json

from app.database.sql_session import SessionLocal
from app.database import crud_user_notes
from app.schemas import chat_schemas
from app.core.agents.archivist import run_archivist

# Configuration du logging pour les tâches Celery
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - (CELERY_TASK) - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

@shared_task(ignore_result=True)
def run_archivist_task(chat_request_json: str, final_response: str):
    """
    Celery task to asynchronously run the Archivist logic.
    """
    logger.info("Archivist task started.")
    db: Session = None
    try:
        db = SessionLocal()
        
        chat_request = chat_schemas.ChatRequest.model_validate_json(chat_request_json)
        
        # 1. Reconstruct the full conversation for the archivist
        full_conversation = chat_request.messages
        full_conversation.append(chat_schemas.ChatMessage(role="assistant", content=final_response))

        # 2. Run the archivist agent to get its decision (this is an async function)
        archivist_decision = asyncio.run(run_archivist(full_conversation=full_conversation))

        # 3. If the archivist decided to create notes, save them to the database
        if archivist_decision and archivist_decision.notes_to_create:
            note_count = len(archivist_decision.notes_to_create)
            logger.info(f"Archivist task: Saving {note_count} new user note(s) to the database.")
            
            # The task is now responsible for the DB write operation
            crud_user_notes.create_user_notes_from_archivist(
                db=db,
                bot_id=chat_request.bot_id,
                discord_user_id=chat_request.user.id,
                notes_to_create=archivist_decision.notes_to_create
            )
        else:
            logger.info("Archivist task: No new information worth saving.")

        logger.info("Archivist task completed successfully.")
    except Exception as e:
        logger.error(f"Error in Archivist task: {e}", exc_info=True)
    finally:
        if db:
            db.close()