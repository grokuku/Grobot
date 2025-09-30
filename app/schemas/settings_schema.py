# app/schemas/settings_schema.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# --- Schéma pour la liste des modèles LLM ---
class LLMModel(BaseModel):
    name: str = Field(..., alias='model')
    modified_at: datetime
    size: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- Schémas pour la gestion des Paramètres Globaux ---

# Schéma de base contenant les champs modifiables des paramètres globaux.
class GlobalSettingsBase(BaseModel):
    decisional_llm_server_url: Optional[str] = Field(None, description="Default server URL for decisional category LLMs.", alias="default_decisional_llm_server")
    decisional_llm_model: Optional[str] = Field(None, description="Default model name for decisional category LLMs.", alias="default_decisional_llm_model")
    decisional_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for decisional LLMs.", alias="default_decisional_llm_context_window")

    tools_llm_server_url: Optional[str] = Field(None, description="Default server URL for tools category LLMs.", alias="default_tool_llm_server")
    tools_llm_model: Optional[str] = Field(None, description="Default model name for tools category LLMs.", alias="default_tool_llm_model")
    tools_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for tools LLMs.", alias="default_tool_llm_context_window")

    output_client_llm_server_url: Optional[str] = Field(None, description="Default server URL for client output category LLMs.", alias="default_output_llm_server")
    output_client_llm_model: Optional[str] = Field(None, description="Default model name for client output category LLMs.", alias="default_output_llm_model")
    output_client_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for client output LLMs.", alias="default_output_llm_context_window")

    multimodal_llm_model: Optional[str] = Field(
        None, description="The name of the multimodal LLM model to use for image analysis."
    )
    context_header_default_prompt: Optional[str] = Field(
        None, description="The default prompt template for the context header."
    )
    tools_system_prompt: Optional[str] = Field(
        None, description="The prompt template to instruct the LLM on how to use tools."
    )
    
    model_config = ConfigDict(populate_by_name=True)


# Schéma utilisé pour la mise à jour des paramètres. Tous les champs sont optionnels.
class GlobalSettingsUpdate(GlobalSettingsBase):
    pass


# Schéma complet pour la lecture des paramètres globaux (ce que l'API retourne).
# CORRECTED: This schema now correctly inherits from GlobalSettingsBase.
# It only adds the 'id' field and the 'from_attributes' config.
# It no longer re-declares fields, which preserves the Optional types and aliases
# from the parent, fixing the validation error when a value is NULL in the DB.
class GlobalSettings(GlobalSettingsBase):
    id: int

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)