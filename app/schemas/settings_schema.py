from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

# --- Schéma pour la liste des modèles LLM ---
class LLMModel(BaseModel):
    name: str = Field(..., alias='model')
    modified_at: Optional[datetime] = None
    size: Optional[int] = None
    description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# --- Schémas pour la gestion des Paramètres Globaux ---

# Schéma de base contenant les champs modifiables des paramètres globaux.
class GlobalSettingsBase(BaseModel):
    decisional_llm_server_url: Optional[str] = Field(None, description="Default server URL for decisional category LLMs.", alias="default_decisional_llm_server")
    decisional_llm_model: Optional[str] = Field(None, description="Default model name for decisional category LLMs.", alias="default_decisional_llm_model")
    decisional_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for decisional LLMs.", alias="default_decisional_llm_context_window")
    decisional_llm_api_key: Optional[str] = Field(None, description="API key for decisional category LLMs.", alias="default_decisional_llm_api_key")

    tools_llm_server_url: Optional[str] = Field(None, description="Default server URL for tools category LLMs.", alias="default_tool_llm_server")
    tools_llm_model: Optional[str] = Field(None, description="Default model name for tools category LLMs.", alias="default_tool_llm_model")
    tools_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for tools LLMs.", alias="default_tool_llm_context_window")
    tools_llm_api_key: Optional[str] = Field(None, description="API key for tools category LLMs.", alias="default_tool_llm_api_key")

    output_client_llm_server_url: Optional[str] = Field(None, description="Default server URL for client output category LLMs.", alias="default_output_llm_server")
    output_client_llm_model: Optional[str] = Field(None, description="Default model name for client output category LLMs.", alias="default_output_llm_model")
    output_client_llm_context_window: Optional[int] = Field(None, gt=0, description="Default context window size for client output LLMs.", alias="default_output_llm_context_window")
    output_client_llm_api_key: Optional[str] = Field(None, description="API key for client output category LLMs.", alias="default_output_llm_api_key")

    multimodal_llm_model: Optional[str] = Field(
        None, description="The name of the multimodal LLM model to use for image analysis."
    )
    multimodal_llm_api_key: Optional[str] = Field(
        None, description="API key for multimodal LLM.", alias="multimodal_llm_api_key"
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


# --- Schemas for LLM Evaluation ---

class LLMEvaluationRunCreate(BaseModel):
    """Schema for creating a new LLM evaluation run."""
    llm_category: str = Field(..., description="The category to evaluate (e.g., 'decisional').")
    llm_server_url: str = Field(..., description="The server URL of the model to evaluate.")
    llm_model_name: str = Field(..., description="The name of the model to evaluate.")
    llm_context_window: Optional[int] = Field(None, gt=0, description="The context window size to use for this evaluation.")


class LLMEvaluationRun(BaseModel):
    """Schema for representing an LLM evaluation run task after creation."""
    task_id: str = Field(..., description="The Celery task ID for this evaluation run.")
    status: str = Field(..., description="The current status of the task (e.g., PENDING).")

    model_config = ConfigDict(from_attributes=True)


class LLMEvaluationRunResult(BaseModel):
    """Schema for returning the results of a single LLM evaluation run."""
    id: int
    task_id: str
    status: str
    
    # --- NEW: Add model name and context window for display ---
    llm_model_name: str
    llm_context_window: Optional[int] = None
    
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    summary_reliability_score: Optional[float] = None
    summary_avg_response_ms: Optional[float] = None
    summary_avg_tokens_per_second: Optional[float] = None
    
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)