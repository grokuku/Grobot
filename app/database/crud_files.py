# app/database/crud_files.py
import os
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
import logging
import json
import asyncio

from app.database import sql_models
from app.schemas import file_schemas
from app.core.llm.ollama_client import OllamaClient
from app.database.crud_settings import get_global_settings

# Configure logger
logger = logging.getLogger(__name__)

def create_file_record(db: Session, file: file_schemas.FileCreate) -> sql_models.UploadedFile:
    """
    Creates a new file record in the database.
    
    Args:
        db: The database session.
        file: The Pydantic schema containing the file data.
        
    Returns:
        The newly created UploadedFile SQLAlchemy model instance.
    """
    # Create the SQLAlchemy model instance from the Pydantic schema
    db_file = sql_models.UploadedFile(**file.model_dump())
    
    # Add to session, commit, and refresh to get the DB-generated values
    db.add(db_file)
    db.commit()
    db.refresh(db_file)
    
    return db_file

def get_file_by_uuid(db: Session, uuid: str) -> Optional[sql_models.UploadedFile]:
    """
    Retrieves a single file record by its UUID, without access control.
    """
    return db.query(sql_models.UploadedFile).filter(sql_models.UploadedFile.uuid == uuid).first()

def get_accessible_file_by_uuid(db: Session, uuid: str, requester_discord_id: str) -> Optional[sql_models.UploadedFile]:
    """
    Retrieves a single file by UUID, but only if the requester has access.
    Access is granted if the file is 'PUBLIC' or the requester is the owner.
    """
    return db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.uuid == uuid,
        sql_models.UploadedFile.storage_status == 'PRESENT',
        or_(
            sql_models.UploadedFile.access_level == 'PUBLIC',
            sql_models.UploadedFile.owner_discord_id == requester_discord_id
        )
    ).first()

# --- NOUVELLES FONCTIONS POUR LES OUTILS MCP ---

def get_file_by_uuid_for_bot(db: Session, uuid: str, bot_id: int) -> Optional[sql_models.UploadedFile]:
    """
    Retrieves a single file by UUID, but only if it belongs to the specified bot.
    Used for bot-centric operations where user access control is not required.
    """
    return db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.uuid == uuid,
        sql_models.UploadedFile.bot_id == bot_id,
        sql_models.UploadedFile.storage_status == 'PRESENT'
    ).first()

def get_all_files_for_bot(db: Session, bot_id: int, limit: int = 100) -> List[sql_models.UploadedFile]:
    """
    Retrieves all active files for a specific bot.
    """
    return db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.bot_id == bot_id,
        sql_models.UploadedFile.storage_status == 'PRESENT'
    ).order_by(sql_models.UploadedFile.created_at.desc()).limit(limit).all()

def search_files_by_query_for_bot(db: Session, bot_id: int, query: str, limit: int = 10) -> List[sql_models.UploadedFile]:
    """
    Searches for files for a specific bot where the query matches filename or description.
    """
    search_term = f"%{query}%"
    return db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.bot_id == bot_id,
        sql_models.UploadedFile.storage_status == 'PRESENT',
        or_(
            sql_models.UploadedFile.filename.ilike(search_term),
            sql_models.UploadedFile.description.ilike(search_term)
        )
    ).order_by(sql_models.UploadedFile.created_at.desc()).limit(limit).all()

def delete_file_record_and_storage(db: Session, db_file: sql_models.UploadedFile) -> sql_models.UploadedFile:
    """
    Performs a hard delete: removes the file from physical storage and then
    deletes the record from the database.
    """
    # 1. Delete the physical file
    if os.path.exists(db_file.storage_path):
        try:
            os.remove(db_file.storage_path)
            logger.info(f"Successfully deleted physical file: {db_file.storage_path}")
        except OSError as e:
            logger.error(f"Error deleting physical file {db_file.storage_path}: {e}")
            # We might choose to raise an exception here to halt the process
            # For now, we log the error and proceed to delete the DB record anyway.
    else:
        logger.warning(f"Physical file not found at {db_file.storage_path}, but proceeding with DB record deletion.")

    # 2. Delete the database record
    db.delete(db_file)
    db.commit()
    return db_file

# --- FIN DES NOUVELLES FONCTIONS ---


def update_file_description(db: Session, db_file: sql_models.UploadedFile, description: str) -> sql_models.UploadedFile:
    """
    Updates the description of a file record and commits the change.
    
    Args:
        db: The database session.
        db_file: The SQLAlchemy model instance of the file to update.
        description: The new description text.
        
    Returns:
        The updated UploadedFile model instance.
    """
    db_file.description = description
    db.commit()
    db.refresh(db_file)
    return db_file

def delete_file_record(db: Session, uuid: str) -> Optional[sql_models.UploadedFile]:
    """
    Soft-deletes a file record by setting its status to 'PURGED'.
    Does not delete the physical file.
    
    Args:
        db: The database session.
        uuid: The UUID of the file to delete.
        
    Returns:
        The updated UploadedFile model instance, or None if not found.
    """
    db_file = get_file_by_uuid(db=db, uuid=uuid)
    if db_file and db_file.storage_status == 'PRESENT':
        db_file.storage_status = 'PURGED'
        db.commit()
        db.refresh(db_file)
        return db_file
    return None


def get_all_files_for_bot_admin(db: Session, bot_id: int, limit: int = 1000) -> List[sql_models.UploadedFile]:
    """
    Admin function to retrieve all files for a specific bot, bypassing user-level access control.
    
    Args:
        db: The database session.
        bot_id: The ID of the bot to retrieve files for.
        limit: The maximum number of results to return.
        
    Returns:
        A list of all UploadedFile model instances for the bot.
    """
    query = db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.bot_id == bot_id,
        sql_models.UploadedFile.storage_status == 'PRESENT'
    )
    return query.order_by(sql_models.UploadedFile.created_at.desc()).limit(limit).all()

def search_files(
    db: Session, 
    bot_id: int, 
    requester_discord_id: str,
    filename: Optional[str] = None,
    file_family: Optional[str] = None,
    owner_id: Optional[str] = None,
    limit: int = 100
) -> List[sql_models.UploadedFile]:
    """
    Searches for files based on criteria, respecting access control.
    
    A user can see a file if:
    - The file's access_level is 'PUBLIC'.
    - OR the requester is the owner of the file.
    
    Args:
        db: The database session.
        bot_id: The ID of the bot to search within.
        requester_discord_id: The Discord ID of the user making the request.
        filename: Optional filter for filename (case-insensitive search).
        file_family: Optional filter for the file family (e.g., 'image', 'text').
        owner_id: Optional filter to search for files of a specific owner.
        limit: The maximum number of results to return.
        
    Returns:
        A list of UploadedFile model instances that match the criteria.
    """
    query = db.query(sql_models.UploadedFile)
    
    # --- Base filters ---
    # Must belong to the correct bot and be physically present
    query = query.filter(sql_models.UploadedFile.bot_id == bot_id)
    query = query.filter(sql_models.UploadedFile.storage_status == 'PRESENT')

    # --- Access Control Filter (CRITICAL) ---
    # The file must be public OR the requester must be the owner.
    query = query.filter(
        or_(
            sql_models.UploadedFile.access_level == 'PUBLIC',
            sql_models.UploadedFile.owner_discord_id == requester_discord_id
        )
    )
    
    # --- Optional search filters ---
    if filename:
        query = query.filter(sql_models.UploadedFile.filename.ilike(f"%{filename}%"))
        
    if file_family:
        query = query.filter(sql_models.UploadedFile.file_family == file_family)
        
    if owner_id:
        query = query.filter(sql_models.UploadedFile.owner_discord_id == owner_id)

    # Order by creation date, newest first
    query = query.order_by(sql_models.UploadedFile.created_at.desc())
    
    # Apply limit
    return query.limit(limit).all()


async def _get_llm_summary(ollama_client: OllamaClient, model: str, system_prompt: str, content: str) -> str:
    """Helper async function to get a summary from the LLM."""
    full_response = ""
    async for chunk in ollama_client.chat_streaming_response(
        model=model,
        system_prompt=system_prompt,
        messages=[{"role": "user", "content": content}]
    ):
        try:
            data = json.loads(chunk)
            if "error" in data:
                raise Exception(data["error"])
            if "message" in data and "content" in data["message"]:
                full_response += data["message"]["content"]
            if data.get("done"):
                break
        except (json.JSONDecodeError, KeyError):
            logger.warning(f"Could not parse a chunk from Ollama stream: {chunk}")
            continue
    return full_response

def analyze_and_update_file_description(db: Session, uuid: str):
    """

    Analyzes a text-based file, generates a summary using an LLM,
    and updates the file's description in the database.
    This function is intended to be run as a background task.
    """
    logger.info(f"Starting analysis for file UUID: {uuid}")
    db_file = get_file_by_uuid(db, uuid)

    if not db_file:
        logger.error(f"Analysis failed: File with UUID {uuid} not found.")
        return

    if db_file.file_family != 'text':
        logger.warning(f"Skipping analysis for non-text file: {uuid} (family: {db_file.file_family})")
        db_file.description = "File is not a text document and cannot be analyzed."
        db.commit()
        return

    try:
        with open(db_file.storage_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading file {db_file.storage_path} for analysis: {e}")
        db_file.description = f"Error: Could not read file content. Reason: {e}"
        db.commit()
        return
        
    settings = get_global_settings(db)
    if not settings or not settings.ollama_host_url:
        logger.error("Ollama host URL not configured in global settings.")
        db_file.description = "Error: Ollama host not configured."
        db.commit()
        return
        
    ollama_client = OllamaClient(host_url=str(settings.ollama_host_url))
    
    system_prompt = (
        "You are an expert file analyst. Your task is to provide a concise summary "
        "of the following file content. The summary should capture the main points, "
        "key topics, and overall purpose of the document. Do not add any preamble "
        "or conclusion, just provide the summary text."
    )
    
    try:
        logger.info(f"Sending content of file {uuid} to LLM for summarization.")
        
        # Since this function is sync, we run the async helper in a new event loop.
        summary = asyncio.run(_get_llm_summary(
            ollama_client=ollama_client,
            model=str(settings.default_llm_model),
            system_prompt=system_prompt,
            content=content
        ))
        
        db_file.description = summary
        logger.info(f"Successfully generated summary for file {uuid}.")

    except Exception as e:
        logger.error(f"Error during LLM call for file {uuid}: {e}")
        db_file.description = f"Error: Failed to generate summary. Reason: {e}"

    finally:
        db.commit()
        logger.info(f"Analysis task finished for file {uuid}.")