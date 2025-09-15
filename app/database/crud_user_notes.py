# app/database/crud_user_notes.py
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import sql_models
from app.schemas import user_note_schemas

def get_user_notes_by_profile_id(db: Session, user_profile_id: int) -> List[sql_models.UserNote]:
    """
    Retrieves all notes for a specific user profile.

    Args:
        db: The database session.
        user_profile_id: The ID of the user profile.

    Returns:
        A list of UserNote objects, ordered by most recent first.
    """
    return db.query(sql_models.UserNote).filter(
        sql_models.UserNote.user_profile_id == user_profile_id
    ).order_by(sql_models.UserNote.created_at.desc()).all()

# SUPPRIMÉ: La fonction get_user_notes_by_user est obsolète. La nouvelle logique passe par le profil.
# SUPPRIMÉ: La fonction get_user_notes_by_user_id est obsolète et n'est plus utilisée.

def create_user_note(db: Session, note: user_note_schemas.UserNoteCreate) -> sql_models.UserNote:
    """
    Creates a new user note in the database.

    Args:
        db: The database session.
        note: The Pydantic schema containing the note data.

    Returns:
        The newly created UserNote object.
    """
    # La logique est la même, mais le schéma 'note' contient maintenant user_profile_id.
    db_note = sql_models.UserNote(**note.model_dump())
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note

def get_note_by_id(db: Session, note_id: int) -> Optional[sql_models.UserNote]:
    """
    Retrieves a single note by its primary key ID.

    Args:
        db: The database session.
        note_id: The ID of the note to retrieve.

    Returns:
        The UserNote object if found, otherwise None.
    """
    return db.query(sql_models.UserNote).filter(sql_models.UserNote.id == note_id).first()

def delete_user_note(db: Session, note_id: int) -> bool:
    """
    Deletes a user note from the database.

    Args:
        db: The database session.
        note_id: The ID of the note to delete.

    Returns:
        True if the note was deleted, False otherwise.
    """
    db_note = get_note_by_id(db, note_id=note_id)
    if db_note:
        db.delete(db_note)
        db.commit()
        return True
    return False