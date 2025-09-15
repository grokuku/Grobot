from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload # NOUVEAU: Import de joinedload
from typing import List, Optional

from app.database.sql_session import get_db
from app.schemas import user_profile_schemas, user_note_schemas
from app.database import crud_user_profiles, crud_user_notes
from app.database import sql_models # NOUVEAU: Import de sql_models

# This router is for bot-specific internal actions
router = APIRouter(
    tags=["User Profiles & Notes (Bot Internal)"]
)

# This router is for UI-facing admin actions
router_admin = APIRouter(
    prefix="/users",
    tags=["User Profiles & Notes (Admin)"]
)

# --- Schemas for API Payloads & Responses ---

class UserProfileWithNotes(user_profile_schemas.UserProfile):
    """
    A combined schema that includes the user's profile (instructions)
    and all associated factual notes.
    """
    notes: List[user_note_schemas.UserNote]

class UserInfoPayload(BaseModel):
    """
    Payload sent by the bot process to update a user's display name and username.
    """
    username: Optional[str] = None
    display_name: Optional[str] = None


# --- Admin-facing Endpoints ---

@router.get(
    "/bots/{bot_id}/users",
    response_model=List[user_profile_schemas.UserProfile],
    summary="List all known users for a bot",
    tags=["User Profiles & Notes (Admin)"] # Override tag for docs clarity
)
def list_users_for_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieves a list of all user profiles that have been created for a specific bot.
    This is used to populate the initial view of the Knowledge Base tab in the UI.
    """
    db_profiles = crud_user_profiles.get_user_profiles_by_bot(db, bot_id=bot_id)
    return db_profiles

# CORRIGÉ: La logique est grandement simplifiée grâce à la nouvelle relation de base de données.
@router.get(
    "/bots/{bot_id}/users/search",
    response_model=List[UserProfileWithNotes],
    summary="Search for users within a bot's knowledge base",
    tags=["User Profiles & Notes (Admin)"]
)
def search_users_for_bot(bot_id: int, query: str, db: Session = Depends(get_db)):
    """
    Searches for users within a specific bot's context by display name, username, or Discord ID.
    Returns a list of matching profiles, each including their associated notes, loaded efficiently.
    """
    # SQLAlchemy charge maintenant les profils ET leurs notes associées en une seule requête optimisée.
    db_profiles = db.query(sql_models.UserProfile).options(
        joinedload(sql_models.UserProfile.notes)
    ).filter(
        sql_models.UserProfile.bot_id == bot_id
    )

    if query.isdigit():
        db_profiles = db_profiles.filter(sql_models.UserProfile.discord_user_id == query)
    else:
        search_term = f"%{query}%"
        db_profiles = db_profiles.filter(
            (sql_models.UserProfile.display_name.ilike(search_term)) |
            (sql_models.UserProfile.username.ilike(search_term))
        )
    
    return db_profiles.all()


# --- Bot-facing Endpoints (Original router) ---

# CORRIGÉ: Simplifié pour utiliser la nouvelle relation.
@router.post(
    "/bots/{bot_id}/servers/{server_id}/users/{user_id}/profile",
    response_model=UserProfileWithNotes,
    summary="Get/create a user profile and optionally update their names"
)
def get_or_create_user_profile_with_notes(
    bot_id: int, 
    server_id: str, 
    user_id: str, 
    user_info: UserInfoPayload, 
    db: Session = Depends(get_db)
):
    """
    Retrieves a user's profile and notes. If the profile doesn't exist, it's created.
    This endpoint also updates the user's username and display_name if they are provided.
    """
    db_profile = crud_user_profiles.get_or_create_user_profile(
        db, 
        bot_id=bot_id, 
        user_id=user_id, 
        server_id=server_id,
        username=user_info.username,
        display_name=user_info.display_name
    )
    
    # Les notes sont maintenant directement accessibles depuis le profil.
    return db_profile

@router.put(
    "/bots/{bot_id}/servers/{server_id}/users/{user_id}/profile",
    response_model=user_profile_schemas.UserProfile,
    summary="Update a user's profile (Admin/Bot)"
)
def update_user_profile_instructions(
    bot_id: int,
    server_id: str,
    user_id: str,
    profile_update: user_profile_schemas.UserProfileUpdate,
    db: Session = Depends(get_db)
):
    db_profile = crud_user_profiles.update_user_profile(
        db, bot_id=bot_id, user_id=user_id, server_id=server_id, profile_update=profile_update
    )
    if not db_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found for this bot, server, and user combination."
        )
    return db_profile

# CORRIGÉ: La logique est simplifiée pour utiliser les nouveaux schémas.
@router.post(
    "/bots/{bot_id}/servers/{server_id}/users/{user_id}/notes",
    response_model=user_note_schemas.UserNote,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new note for a user (Bot)"
)
def create_new_user_note(
    bot_id: int,
    server_id: str,
    user_id: str,
    note: user_note_schemas.UserNoteBase, # Utilise UserNoteBase qui ne contient pas d'infos de profil
    db: Session = Depends(get_db)
):
    """
    Creates a new note and attaches it to the correct user profile.
    """
    # D'abord, on s'assure que le profil de l'utilisateur existe.
    profile = crud_user_profiles.get_or_create_user_profile(
        db, bot_id=bot_id, server_id=server_id, user_id=user_id
    )

    # On crée l'objet de la note avec l'ID du profil.
    note_data = user_note_schemas.UserNoteCreate(
        user_profile_id=profile.id,
        **note.model_dump()
    )
    return crud_user_notes.create_user_note(db, note=note_data)

@router_admin.delete(
    "/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user note (Admin)"
)
def delete_a_user_note(note_id: int, db: Session = Depends(get_db)):
    success = crud_user_notes.delete_user_note(db, note_id=note_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Note with ID {note_id} not found."
        )
    return None