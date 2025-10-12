from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

# --- Trigger Schemas ---

class TriggerBase(BaseModel):
    trigger_type: str = Field(default="cron", description="The type of the trigger")
    config: Dict[str, Any] = Field(default_factory=dict, description="Trigger configuration, e.g., {'cron_schedule': '0 8 * * *'}")

class TriggerCreate(TriggerBase):
    pass

class Trigger(TriggerBase):
    id: int
    workflow_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- WorkflowStep Schemas ---

class WorkflowStepBase(BaseModel):
    # --- MODIFICATION START ---
    # mcp_server_id can be 0 from the frontend, and will be Optional[int] in the response
    mcp_server_id: Optional[int] = Field(
        None, 
        description="The ID of the MCP server, or null for internal tools."
    )
    # --- MODIFICATION END ---
    tool_name: str = Field(..., description="The name of the tool to be executed")
    parameter_mappings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Defines how to map inputs for this step. Can be a static value or a reference to a previous step's output."
    )

class WorkflowStepCreate(WorkflowStepBase):
    step_order: int

class WorkflowStep(WorkflowStepBase):
    id: int
    workflow_id: int
    step_order: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Workflow Schemas ---

class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_enabled: bool = True

class WorkflowCreate(WorkflowBase):
    trigger: TriggerCreate
    steps: List[WorkflowStepCreate]

class Workflow(WorkflowBase):
    id: int
    bot_id: int
    trigger: Trigger
    steps: List[WorkflowStep]
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Workflow Output Schemas ---

class WorkflowOutputAttachment(BaseModel):
    """Schema for a single attachment in a workflow output."""
    data: str
    filename: Optional[str] = None

class WorkflowOutputDiscord(BaseModel):
    bot_id: int
    channel_id: str
    message_content: Optional[str] = None
    attachments: Optional[List[WorkflowOutputAttachment]] = None