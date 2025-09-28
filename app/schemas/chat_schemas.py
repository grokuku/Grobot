"""
Pydantic schemas for chat interactions, supporting the new agent chain architecture.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

# region: API Request Schemas
# ==============================================================================

class ChatMessage(BaseModel):
    """Represents a single message in the conversation history."""
    role: str  # e.g., "user", "assistant", "tool"
    content: str

class ProcessMessageRequest(BaseModel):
    """Request body for the main chat processing endpoint."""
    bot_id: int
    user_id: str  # Discord user ID
    user_display_name: str
    channel_id: str
    message_id: str
    message_content: str
    history: List[ChatMessage]
    is_direct_message: bool = False
    is_direct_mention: bool = False # NEW: Flag to indicate a direct mention or reply

# endregion

# region: Agent & Plan Schemas
# ==============================================================================

class GatekeeperDecision(BaseModel):
    """Schema for the Gatekeeper's output."""
    reason: str
    should_respond: bool = False

class RequiredTool(BaseModel):
    """Schema for a single required tool."""
    tool_name: str
    arguments: Dict[str, Any]

class ToolIdentifierResult(BaseModel):
    """Schema for the Tool Identifier's output."""
    required_tools: List[str] = []

class MissingParameter(BaseModel):
    """Schema for a single missing parameter."""
    tool: str
    parameter: str

class ParameterExtractorResult(BaseModel):
    """Schema for the Parameter Extractor's output."""
    extracted_parameters: Dict[str, Dict[str, Any]] = {}
    missing_parameters: List[MissingParameter] = []
    clarification_question: Optional[str] = None

class PlanStep(BaseModel):
    """A single step in an execution plan."""
    step: int
    tool_name: str
    arguments: Dict[str, Any]

class PlannerResult(BaseModel):
    """Schema for the Planner's output."""
    plan: List[PlanStep] = []

# endregion

# region: API Response Schemas
# ==============================================================================

class BaseChatResponse(BaseModel):
    """Base schema for all actions returned by the chat processing endpoint."""
    action: str
    
class StopResponse(BaseChatResponse):
    """Action to tell the client to stop processing."""
    action: Literal["STOP"] = "STOP"
    reason: str

class ClarifyResponse(BaseChatResponse):
    """Action to ask the user for more information."""
    action: Literal["CLARIFY"] = "CLARIFY"
    message: str

class AcknowledgeAndExecuteResponse(BaseChatResponse):
    """
    Action to send an acknowledgement message and then execute a plan.
    The plan is now passed along with this response object to be saved in Redis.
    """
    action: Literal["ACKNOWLEDGE_AND_EXECUTE"] = "ACKNOWLEDGE_AND_EXECUTE"
    acknowledgement_message: str
    final_response_stream_url: str # URL the client will connect to for the final answer
    
    # === MODIFICATION START: Add fields to carry the execution context ===
    plan: Optional[PlannerResult] = None
    tool_definitions: List[Dict[str, Any]] = []
    # === MODIFICATION END ===

class SynthesizeResponse(BaseChatResponse):
    """Action to stream the final response directly."""
    action: Literal["SYNTHESIZE"] = "SYNTHESIZE"
    final_response_stream_url: str

# endregion

# region: Archivist Schemas (Kept from previous version)
# ==============================================================================
class NoteToCreate(BaseModel):
    fact: str
    reliability_score: int = Field(..., ge=1, le=10)

class ArchivistDecision(BaseModel):
    notes_to_create: List[NoteToCreate] = []

class ArchiveRequest(BaseModel):
    bot_id: int
    user_id: str
    user_display_name: str
    conversation_history: List[ChatMessage]

# endregion