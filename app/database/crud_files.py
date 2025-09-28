import os
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
import logging

from app.database import sql_models
from app.schemas import file_schemas

# Configure logger
logger = logging.getLogger(__name__)

def create_file_record(db: Session, file: file_schemas.FileCreate) -> sql_models.UploadedFile:
    """
    Creates a new file record in the database.
    """
    db_file = sql_models.UploadedFile(**file.model_dump())
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
    """
    return db.query(sql_models.UploadedFile).filter(
        sql_models.UploadedFile.uuid == uuid,
        sql_models.UploadedFile.storage_status == 'PRESENT',
        or_(
            sql_models.UploadedFile.access_level == 'PUBLIC',
            sql_models.UploadedFile.owner_discord_id == requester_discord_id
        )
    ).first()

def get_file_by_uuid_for_bot(db: Session, uuid: str, bot_id: int) -> Optional[sql_models.UploadedFile]:
    """
    Retrieves a single file by UUID, but only if it belongs to the specified bot.
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
    if os.path.exists(db_file.storage_path):
        try:
            os.remove(db_file.storage_path)
            logger.info(f"Successfully deleted physical file: {db_file.storage_path}")
        except OSError as e:
            logger.error(f"Error deleting physical file {db_file.storage_path}: {e}")
    else:
        logger.warning(f"Physical file not found at {db_file.storage_path}, but proceeding with DB record deletion.")

    db.delete(db_file)
    db.commit()
    return db_file

def update_file_description(db: Session, db_file: sql_models.UploadedFile, description: str) -> sql_models.UploadedFile:
    """
    Updates the description of a file record and commits the change.
    """
    db_file.description = description
    db.commit()
    db.refresh(db_file)
    return db_file

def delete_file_record(db: Session, uuid: str) -> Optional[sql_models.UploadedFile]:
    """
    Soft-deletes a file record by setting its status to 'PURGED'.
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
    Admin function to retrieve all files for a specific bot.
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
    """
    query = db.query(sql_models.UploadedFile)
    
    query = query.filter(sql_models.UploadedFile.bot_id == bot_id)
    query = query.filter(sql_models.UploadedFile.storage_status == 'PRESENT')

    query = query.filter(
        or_(
            sql_models.UploadedFile.access_level == 'PUBLIC',
            sql_models.UploadedFile.owner_discord_id == requester_discord_id
        )
    )
    
    if filename:
        query = query.filter(sql_models.UploadedFile.filename.ilike(f"%{filename}%"))
    if file_family:
        query = query.filter(sql_models.UploadedFile.file_family == file_family)
    if owner_id:
        query = query.filter(sql_models.UploadedFile.owner_discord_id == owner_id)

    query = query.order_by(sql_models.UploadedFile.created_at.desc())
    return query.limit(limit).all()