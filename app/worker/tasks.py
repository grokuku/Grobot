# app/worker/tasks.py
import logging
import asyncio
from celery import shared_task
from sqlalchemy.orm import Session
import json

from app.database.sql_session import SessionLocal
from app.schemas import chat_schemas
from app.core import agent_logic

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
    Tâche Celery pour exécuter la logique de l'Archiviste de manière asynchrone.
    """
    logger.info("Archivist task started.")
    db: Session = None
    try:
        db = SessionLocal()
        
        chat_request = chat_schemas.ChatRequest.model_validate_json(chat_request_json)
        
        # Exécute la fonction asynchrone de l'Archiviste depuis le contexte synchrone de Celery
        asyncio.run(agent_logic.run_archivist(db, chat_request, final_response))
        
        logger.info("Archivist task completed successfully.")
    except Exception as e:
        logger.error(f"Error in Archivist task: {e}", exc_info=True)
    finally:
        if db:
            db.close()