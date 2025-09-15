# app/schemas/user_note_schemas.py
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class UserNoteBase(BaseModel):
    """
    Base schema for a user note. The author is tracked.
    """
    author_discord_id: str
    note_content: str
    reliability_score: int = Field(ge=0, le=100, default=50)

class UserNoteCreate(UserNoteBase):
    """
    Schema used for creating a new user note in the database.
    It's linked directly to a user profile.
    """
    user_profile_id: int

class UserNoteUpdate(BaseModel):
    """
    Schema for updating an existing user note. All fields are optional.
    """
    note_content: Optional[str] = None
    reliability_score: Optional[int] = Field(ge=0, le=100, default=None)

class UserNote(UserNoteBase):
    """
    Schema for returning a user note from the API, including all database-generated fields.
    """
    id: int
    user_profile_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)