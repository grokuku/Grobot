# app/schemas/bot_schemas.py
from pydantic import BaseModel, Field, ConfigDict, computed_field
from typing import Optional, Dict, Any, List
from datetime import datetime

# --- NOUVEAU: Schémas pour les paramètres de salon ---
class ChannelSettingsBase(BaseModel):
    has_access: bool = Field(True, description="Determines if the bot can operate in this channel at all.")
    passive_listening: bool = Field(True, description="Determines if the bot should listen to non-mention messages.")

class ChannelSettingsCreate(ChannelSettingsBase):
    pass

class ChannelSettingsUpdate(ChannelSettingsBase):
    has_access: Optional[bool] = None
    passive_listening: Optional[bool] = None

class ChannelSettings(ChannelSettingsBase):
    id: int
    bot_id: int
    channel_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# --- Schémas pour la gestion des Serveurs MCP ---
# Schéma de base pour un serveur MCP, utilisé pour l'imbrication.
class MCPServerInDB(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    host: str
    port: int
    enabled: bool

    model_config = ConfigDict(from_attributes=True)

# NOUVEAU: Schéma représentant une association complète, incluant la configuration.
class MCPServerAssociationDetails(MCPServerInDB):
    """
    Represents an MCP Server as associated with a Bot, including the
    specific configuration for that association.
    """
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Configuration JSON for this server on a specific bot.")



# --- Schémas pour la gestion des Bots ---

class BotCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="Unique name of the bot.")
    discord_token: Optional[str] = Field(None, min_length=10, description="Discord token for the bot. Optional.")
    system_prompt: Optional[str] = ""
    personality: Optional[str] = ""
    passive_listening_enabled: Optional[bool] = False
    gatekeeper_history_limit: Optional[int] = Field(5, gt=0, description="Number of past messages to provide to the Gatekeeper.")
    conversation_history_limit: Optional[int] = Field(15, gt=0, description="Number of past messages to provide for full conversation context.")
    
    # New categorized LLM settings
    decisional_llm_server_url: Optional[str] = None
    decisional_llm_model: Optional[str] = None
    decisional_llm_context_window: Optional[int] = Field(None, gt=0)
    decisional_llm_api_key: Optional[str] = None  # NEW: API key for decisional LLM
    
    tools_llm_server_url: Optional[str] = None
    tools_llm_model: Optional[str] = None
    tools_llm_context_window: Optional[int] = Field(None, gt=0)
    tools_llm_api_key: Optional[str] = None  # NEW: API key for tools LLM
    
    output_client_llm_server_url: Optional[str] = None
    output_client_llm_model: Optional[str] = None
    output_client_llm_context_window: Optional[int] = Field(None, gt=0)
    output_client_llm_api_key: Optional[str] = None  # NEW: API key for output client LLM

    multimodal_llm_model: Optional[str] = None
    multimodal_llm_api_key: Optional[str] = None  # NEW: API key for multimodal LLM

class BotUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    system_prompt: Optional[str] = Field(None)
    personality: Optional[str] = Field(None)
    discord_token: Optional[str] = Field(None, min_length=10)
    is_active: Optional[bool] = None
    passive_listening_enabled: Optional[bool] = None
    gatekeeper_history_limit: Optional[int] = Field(None, gt=0)
    conversation_history_limit: Optional[int] = Field(None, gt=0)

    llm_provider: Optional[str] = Field(None, max_length=50)

    # New categorized LLM settings
    decisional_llm_server_url: Optional[str] = None
    decisional_llm_model: Optional[str] = None
    decisional_llm_context_window: Optional[int] = Field(None, gt=0)
    decisional_llm_api_key: Optional[str] = None  # NEW: API key for decisional LLM
    
    tools_llm_server_url: Optional[str] = None
    tools_llm_model: Optional[str] = None
    tools_llm_context_window: Optional[int] = Field(None, gt=0)
    tools_llm_api_key: Optional[str] = None  # NEW: API key for tools LLM
    
    output_client_llm_server_url: Optional[str] = None
    output_client_llm_model: Optional[str] = None
    output_client_llm_context_window: Optional[int] = Field(None, gt=0)
    output_client_llm_api_key: Optional[str] = None  # NEW: API key for output client LLM

    multimodal_llm_model: Optional[str] = None
    multimodal_llm_api_key: Optional[str] = None  # NEW: API key for multimodal LLM
    
    settings: Optional[Dict[str, Any]] = None

class Bot(BaseModel):
    id: int
    name: str
    discord_token: Optional[str] = None
    is_active: bool
    passive_listening_enabled: bool
    gatekeeper_history_limit: int
    conversation_history_limit: int
    system_prompt: str
    personality: str
    llm_provider: str

    # New categorized LLM settings (all optional, can be null if using global settings)
    decisional_llm_server_url: Optional[str] = None
    decisional_llm_model: Optional[str] = None
    decisional_llm_context_window: Optional[int] = None
    decisional_llm_api_key: Optional[str] = None  # NEW: API key for decisional LLM
    
    tools_llm_server_url: Optional[str] = None
    tools_llm_model: Optional[str] = None
    tools_llm_context_window: Optional[int] = None
    tools_llm_api_key: Optional[str] = None  # NEW: API key for tools LLM
    
    output_client_llm_server_url: Optional[str] = None
    output_client_llm_model: Optional[str] = None
    output_client_llm_context_window: Optional[int] = None
    output_client_llm_api_key: Optional[str] = None  # NEW: API key for output client LLM

    multimodal_llm_model: Optional[str] = None
    multimodal_llm_api_key: Optional[str] = None  # NEW: API key for multimodal LLM

    mcp_servers: List[MCPServerAssociationDetails] = []

    channel_settings: List[ChannelSettings] = [] # AJOUT: inclure les paramètres de salon

    @computed_field
    @property
    def mcp_server_ids(self) -> List[int]:
        return [server.id for server in self.mcp_servers]

    settings: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# Schéma pour la configuration complète d'un bot, incluant les données sensibles
class BotConfig(Bot):
    tools_system_prompt: Optional[str] = None

    @computed_field
    @property
    def mcp_server_urls(self) -> List[Dict[str, Any]]:
        urls_with_config = []
        for server in self.mcp_servers:
            if server.enabled:
                urls_with_config.append({
                    "url": f"http://{server.host}:{server.port}",
                    "configuration": server.configuration
                })
        return urls_with_config

# --- Schémas pour la Mémoire du Bot (ChromaDB) ---

class BotMemoryItem(BaseModel):
    """Represents a single item stored in a bot's memory collection."""
    id: str = Field(..., description="The unique ID of the memory item.")
    document: str = Field(..., description="The text content of the memory item.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Associated metadata for the memory item.")

class BotMemory(BaseModel):
    """Represents the entire memory content for a bot."""
    count: int = Field(..., description="The total number of items in the memory.")
    items: List[BotMemoryItem] = Field(..., description="The list of memory items.")


# --- Schema for Log Messages ---

class LogMessage(BaseModel):
    timestamp: str
    source: str
    level: str
    message: str