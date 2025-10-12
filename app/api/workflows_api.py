#// FICHIER: app/api/workflows_api.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging # Importer le module logging
import json # Importer le module json

from ..database import crud_workflows, sql_session, crud_bots, crud_mcp
from ..schemas import workflow_schemas
from ..api import mcp_api # Assuming mcp_api has logic to fetch tools
from ..core.websocket_manager import websocket_manager # Placeholder for the WebSocket manager

# --- LOGGING SETUP ---
logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["Workflows"]
)

# Dependency to get the DB session
def get_db():
    db = sql_session.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Definition of the virtual output tool ---
DISCORD_OUTPUT_TOOL_DEFINITION = {
    "mcp_server_id": 0, # Using 0 to signify an internal tool
    "tool_definition": {
        "name": "post_to_discord",
        "title": "Post to Discord",
        "description": "Posts a message and/or up to 10 attachments to a specified Discord channel.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "title": "Channel ID",
                    "description": "The ID of the Discord channel to post the message to."
                },
                "message_content": {
                    "type": "string",
                    "title": "Message Content",
                    "description": "The text content of the message. Can be left empty if only sending attachments."
                },
                "attachments": {
                    "type": "array",
                    "title": "Attachments",
                    "description": "A list of attachments to send. Supports up to 10.",
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "string",
                                "title": "Attachment Data",
                                "description": "The data for the attachment. Can be raw text, or a URL to an image/file."
                            },
                            "filename": {
                                "type": "string",
                                "title": "Attachment Filename",
                                "description": "Optional: The name for the file. If not provided and data is a URL, it will be auto-detected."
                            }
                        },
                        "required": ["data"]
                    }
                }
            },
            "required": ["channel_id"]
        }
    }
}


@router.get("/bots/{bot_id}/workflow-tools", response_model=List[Dict[str, Any]])
async def get_available_workflow_tools(bot_id: int, db: Session = Depends(get_db)):
    """
    Get all available tools for a bot's workflow, including real MCP tools and internal output tools.
    """
    # Step 1: Fetch all real tools from associated MCP servers
    all_tools = await mcp_api.get_all_tools_for_bot_internal(bot_id=bot_id, db=db)

    # Step 2: Add our virtual Discord output tool to the list
    all_tools.append(DISCORD_OUTPUT_TOOL_DEFINITION)

    return all_tools

@router.get("/bots/{bot_id}/discord-channels", response_model=List[Dict[str, str]])
async def get_discord_channels(bot_id: int):
    """
    Get a list of text channels for a specific bot.
    This requires a live connection to the bot process.
    """
    request_data = {"action": "get_channels"}
    try:
        # This assumes the websocket_manager can handle request-response
        channels = await websocket_manager.request(bot_id, request_data)
        return channels
    except Exception as e:
        # Handle cases where the bot is not connected
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not communicate with bot {bot_id}. It might be offline. Error: {e}"
        )

@router.post("/workflows/outputs/discord", status_code=status.HTTP_202_ACCEPTED)
async def forward_workflow_output_to_discord(output: workflow_schemas.WorkflowOutputDiscord):
    """
    Receives a request from a Celery worker to post a message to Discord
    and forwards it to the appropriate bot process via WebSocket.
    """
    # --- LOGGING ADDED ---
    logger.info(f"Received request to forward output. Payload: {output.model_dump_json(indent=2)}")
    # --- END LOGGING ---

    message_data = {
        "action": "post_to_channel",
        "payload": output.model_dump(exclude={"bot_id"})
    }
    try:
        await websocket_manager.send_to_bot(output.bot_id, message_data)
        return {"message": "Output forwarded to bot for delivery."}
    except Exception as e:
        # This could happen if the bot disconnects while the workflow is running
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not communicate with bot {output.bot_id}. It might be offline. Error: {e}"
        )

@router.post("/bots/{bot_id}/workflows", response_model=workflow_schemas.Workflow, status_code=status.HTTP_201_CREATED)
def create_workflow_for_bot(bot_id: int, workflow: workflow_schemas.WorkflowCreate, db: Session = Depends(get_db)):
    """
    Create a new workflow for a specific bot.
    """
    db_bot = crud_bots.get_bot(db, bot_id=bot_id)
    if not db_bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    return crud_workflows.create_workflow(db=db, bot_id=bot_id, workflow=workflow)

@router.get("/bots/{bot_id}/workflows", response_model=List[workflow_schemas.Workflow])
def read_workflows_for_bot(bot_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all workflows for a specific bot.
    """
    workflows = crud_workflows.get_workflows_by_bot(db, bot_id=bot_id)
    return workflows

@router.get("/workflows/{workflow_id}", response_model=workflow_schemas.Workflow)
def read_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """
    Retrieve a single workflow by its ID.
    """
    db_workflow = crud_workflows.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return db_workflow

# --- NEW ROUTE ---
@router.put("/workflows/{workflow_id}", response_model=workflow_schemas.Workflow)
def update_workflow(workflow_id: int, workflow: workflow_schemas.WorkflowCreate, db: Session = Depends(get_db)):
    """
    Update an existing workflow.
    This will replace the workflow's name, description, and all of its steps.
    """
    db_workflow = crud_workflows.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return crud_workflows.update_workflow(db=db, workflow_id=workflow_id, workflow_update=workflow)

@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: int, db: Session = Depends(get_db)):
    """
    Delete a workflow by its ID.
    """
    db_workflow = crud_workflows.delete_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # For a 204 response, the body is not sent, so we return None.
    return None

@router.post("/workflows/{workflow_id}/run", status_code=status.HTTP_202_ACCEPTED)
def run_workflow_manually(workflow_id: int, db: Session = Depends(get_db)):
    """
    Manually trigger a workflow execution.
    (This will be connected to a Celery task later)
    """
    db_workflow = crud_workflows.get_workflow(db, workflow_id=workflow_id)
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # TODO: Placeholder for Celery task call
    from ..worker.tasks import execute_workflow
    execute_workflow.delay(workflow_id=db_workflow.id)
    
    return {"message": "Workflow execution has been triggered."}