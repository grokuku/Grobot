# Fichier: app/schemas/mcp_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import datetime

# --- Base Schemas ---
class MCPServerBase(BaseModel):
    """
    Base schema for an MCP server, containing common attributes.
    """
    name: str = Field(..., description="Human-readable name for the MCP server.")
    description: Optional[str] = Field(None, description="A brief description of the tools provided by the server.")
    host: str = Field(..., description="Hostname or Docker service name for the server.")
    port: int = Field(..., description="Port on which the server listens.")
    rpc_endpoint_path: str = Field("/mcp", description="The specific path for the JSON-RPC endpoint (e.g., /mcp, /rpc).")
    enabled: bool = Field(True, description="Whether the server is globally enabled and should be managed by the launcher.")

# --- Schemas for API Operations ---
class MCPServerCreate(MCPServerBase):
    """
    Schema used for creating a new MCP server via the API.
    """
    pass

class MCPServerUpdate(BaseModel):
    """
    Schema for updating an existing MCP server. All fields are optional.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    rpc_endpoint_path: Optional[str] = None
    enabled: Optional[bool] = None

class MCPServerInDB(MCPServerBase):
    """
    Schema representing an MCP server as it is stored in the database,
    including read-only fields.
    """
    id: int
    created_at: datetime.datetime
    # SOLUTION: Make updated_at optional to match the Bot schema's behavior.
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class MCPServerAssociationConfig(BaseModel):
    """
    Schema for associating an MCP server with a bot, including specific configuration.
    Used as input when updating a bot's tool configuration.
    """
    mcp_server_id: int = Field(..., description="The ID of the MCP server to associate.")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="A JSON object for tool-specific configuration.")