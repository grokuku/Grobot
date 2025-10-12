####
# FICHIER: app/database/crud_workflows.py
####
from sqlalchemy.orm import Session, joinedload
from typing import List

from . import sql_models
from ..schemas import workflow_schemas


def create_workflow(db: Session, bot_id: int, workflow: workflow_schemas.WorkflowCreate) -> sql_models.Workflow:
    """
    Creates a new workflow with its associated trigger and steps in a single transaction.
    """
    # Create the main Workflow object
    db_workflow = sql_models.Workflow(
        bot_id=bot_id,
        name=workflow.name,
        description=workflow.description,
        is_enabled=workflow.is_enabled
    )

    # Create the associated Trigger object
    db_trigger = sql_models.Trigger(
        trigger_type=workflow.trigger.trigger_type,
        config=workflow.trigger.config,
        workflow=db_workflow  # Associate it with the workflow
    )

    # Create the associated WorkflowStep objects
    db_steps = []
    for step_data in workflow.steps:
        # --- MODIFICATION START ---
        # Convert our conventional mcp_server_id=0 for internal tools to a database-friendly NULL.
        server_id_to_save = None if step_data.mcp_server_id == 0 else step_data.mcp_server_id
        # --- MODIFICATION END ---
        
        db_step = sql_models.WorkflowStep(
            mcp_server_id=server_id_to_save,
            step_order=step_data.step_order,
            tool_name=step_data.tool_name,
            parameter_mappings=step_data.parameter_mappings,
            workflow=db_workflow  # Associate it with the workflow
        )
        db_steps.append(db_step)

    db.add(db_workflow)
    # The trigger and steps are automatically added to the session
    # through the relationship cascade, but being explicit can be clearer.
    db.add(db_trigger)
    db.add_all(db_steps)
    
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def get_workflow(db: Session, workflow_id: int) -> sql_models.Workflow | None:
    """
    Retrieves a single workflow by its ID, including its trigger and steps.
    """
    return db.query(sql_models.Workflow).options(
        joinedload(sql_models.Workflow.trigger),
        joinedload(sql_models.Workflow.steps)
    ).filter(sql_models.Workflow.id == workflow_id).first()


def get_workflows_by_bot(db: Session, bot_id: int) -> List[sql_models.Workflow]:
    """
    Retrieves all workflows for a specific bot.
    """
    return db.query(sql_models.Workflow).filter(sql_models.Workflow.bot_id == bot_id).order_by(sql_models.Workflow.name).all()


# --- FINAL CORRECTED FUNCTION ---
def update_workflow(db: Session, workflow_id: int, workflow_update: workflow_schemas.WorkflowCreate) -> sql_models.Workflow:
    """
    Updates an existing workflow by replacing its attributes, trigger, and steps.
    """
    db_workflow = get_workflow(db, workflow_id=workflow_id)
    if not db_workflow:
        return None

    # 1. Update the main workflow object's attributes
    db_workflow.name = workflow_update.name
    db_workflow.description = workflow_update.description
    db_workflow.is_enabled = workflow_update.is_enabled

    # 2. Update the associated trigger
    if db_workflow.trigger:
        db_workflow.trigger.trigger_type = workflow_update.trigger.trigger_type
        db_workflow.trigger.config = workflow_update.trigger.config
    else:
        db_trigger = sql_models.Trigger(
            trigger_type=workflow_update.trigger.trigger_type,
            config=workflow_update.trigger.config,
            workflow=db_workflow
        )
        db.add(db_trigger)

    # 3. Explicitly delete old steps and flush the change to the database.
    # This ensures DELETEs are executed before the subsequent INSERTs.
    db_workflow.steps.clear()
    db.flush()

    # 4. Create and add the new steps to the now-empty collection.
    for step_data in workflow_update.steps:
        server_id_to_save = None if step_data.mcp_server_id == 0 else step_data.mcp_server_id
        new_step = sql_models.WorkflowStep(
            mcp_server_id=server_id_to_save,
            step_order=step_data.step_order,
            tool_name=step_data.tool_name,
            parameter_mappings=step_data.parameter_mappings
        )
        db_workflow.steps.append(new_step)

    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def delete_workflow(db: Session, workflow_id: int) -> sql_models.Workflow | None:
    """
    Deletes a workflow by its ID. The cascade will handle deleting related triggers and steps.
    """
    db_workflow = get_workflow(db, workflow_id)
    if db_workflow:
        db.delete(db_workflow)
        db.commit()
    return db_workflow