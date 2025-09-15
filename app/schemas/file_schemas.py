# app/schemas/file_schemas.py

from pydantic import BaseModel, Field, ConfigDict, computed_field
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

class FileBase(BaseModel):
    """Base schema for a file with common attributes."""
    filename: str
    file_type: str
    file_family: str
    file_size_bytes: int
    access_level: str = 'PRIVATE'
    file_metadata: Optional[Dict[str, Any]] = None
    description: Optional[str] = None


class FileCreate(FileBase):
    """Schema for creating a new file record."""
    owner_discord_id: str
    bot_id: int
    storage_path: str
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))


class FileUpdate(BaseModel):
    """Schema for updating a file's attributes. All fields are optional."""
    access_level: Optional[str] = None
    description: Optional[str] = None
    last_accessed_at: Optional[datetime] = None


class File(FileBase):
    """Schema for representing a file record in API responses."""
    id: int
    uuid: str
    bot_id: int
    owner_discord_id: str
    storage_status: str
    created_at: datetime
    last_accessed_at: Optional[datetime] = None

    # Pydantic V2 config to allow mapping from ORM models
    model_config = ConfigDict(from_attributes=True)
class FileDescriptionResponse(BaseModel):
 """Schema for the response of the describe-image endpoint."""
 uuid: str
 description: str
 is_from_cache: bool

# NOUVEAU: Schéma pour la réponse détaillée d'un fichier, destiné à l'outil get_file_details
class FileDetails(BaseModel):
    """Detailed information about a file for tool consumption."""
    uuid: str
    filename: str
    file_type: str
    size_bytes: int
    analysis_content: Optional[str] = "No analysis available."

    model_config = ConfigDict(from_attributes=True)