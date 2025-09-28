# app/schemas/settings_schema.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List
from datetime import datetime

# --- Schéma pour la liste des modèles LLM ---
class LLMModel(BaseModel):
    # =================================================================
    #          *** CORRECTION FINALE DU BUG DE VALIDATION ***
    # =================================================================
    # On dit à Pydantic de chercher la valeur dans le champ 'model'
    # de la source et de l'utiliser pour remplir notre champ 'name'.
    name: str = Field(..., alias='model')
    modified_at: datetime
    size: int

    # Configuration Pydantic V2 pour permettre le mapping depuis un
    # objet (from_attributes) et l'utilisation des alias (populate_by_name).
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    # =================================================================

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