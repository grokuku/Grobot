# app/schemas/user_profile_schemas.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# NOUVELLE CLASSE DE BASE
class UserBase(BaseModel):
    """
    The absolute base for a user, containing only their core identity.
    Used for search results.
    """
    discord_user_id: str
    display_name: Optional[str] = "Unknown"
    username: Optional[str] = "unknown"

class UserProfileBase(BaseModel):
    """
    Base schema for a user profile, containing fields that can be set on creation or update.
    """
    discord_user_id: str
    server_discord_id: str
    behavioral_instructions: Optional[str] = "Interact with the user normally."
    # MODIFIÉ: Ajout des champs pour le nom d'utilisateur afin de permettre leur stockage.
    username: Optional[str] = None
    display_name: Optional[str] = None

class UserProfileCreate(UserProfileBase):
    """
    Schema used for creating a new user profile in the database.
    Inherits all fields from UserProfileBase.
    """
    bot_id: int

class UserProfileUpdate(BaseModel):
    """
    Schema for updating an existing user profile. All fields are optional.
    """
    behavioral_instructions: Optional[str] = None

class UserProfile(UserProfileBase):
    """
    Schema for returning a user profile from the API.
    Includes database-generated fields like id, bot_id, and timestamps.
    """
    id: int
    bot_id: int
    created_at: datetime
    # MODIFIÉ: Le champ updated_at est maintenant optionnel pour correspondre au modèle de la BDD.
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)