# app/schemas/settings_schema.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List
from datetime import datetime

# --- Schéma pour la liste des modèles LLM ---
class LLMModel(BaseModel):
    name: str
    modified_at: datetime
    size: int

# --- Schémas pour la gestion des Paramètres Globaux ---

# Schéma de base contenant les champs modifiables des paramètres globaux.
class GlobalSettingsBase(BaseModel):
    ollama_host_url: Optional[str] = Field(
        None, description="URL de base pour joindre le serveur Ollama par défaut."
    )
    default_llm_model: Optional[str] = Field(
        None, description="The name of the default LLM model to use for all bots."
    )
    multimodal_llm_model: Optional[str] = Field(
        None, description="The name of the multimodal LLM model to use for image analysis."
    )
    context_header_default_prompt: Optional[str] = Field(
        None, description="The default prompt template for the context header."
    )
    tools_system_prompt: Optional[str] = Field(
        None, description="The prompt template to instruct the LLM on how to use tools."
    )


# Schéma utilisé pour la mise à jour des paramètres. Tous les champs sont optionnels.
class GlobalSettingsUpdate(GlobalSettingsBase):
    pass


# Schéma complet pour la lecture des paramètres globaux (ce que l'API retourne).
class GlobalSettings(GlobalSettingsBase):
    id: int
    ollama_host_url: str
    default_llm_model: str
    multimodal_llm_model: str
    context_header_default_prompt: str
    tools_system_prompt: str

    # Configuration Pydantic V2 pour permettre le mapping depuis un modèle ORM
    model_config = ConfigDict(from_attributes=True)