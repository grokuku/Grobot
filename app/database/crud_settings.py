from sqlalchemy.orm import Session
from typing import List
from app.database.sql_models import GlobalSettings, LLMEvaluationRun
from app.schemas.settings_schema import (
    GlobalSettingsUpdate,
    GlobalSettings as GlobalSettingsSchema,
    LLMEvaluationRunCreate,
    LLMEvaluationRunResult
)

def get_global_settings(db: Session) -> GlobalSettingsSchema:
    """
    Retrieves the global settings of the application.
    If a configuration does not exist yet, creates one with the
    default values from the model and returns it.
    """
    db_settings = db.query(GlobalSettings).first()

    if not db_settings:
        # If the table is empty, create the first configuration
        db_settings = GlobalSettings()
        db.add(db_settings)
        db.commit()
        db.refresh(db_settings)
        
    return db_settings


def save_global_settings(db: Session, settings_update: GlobalSettingsUpdate) -> GlobalSettingsSchema:
    """
    Updates the global settings of the application.
    """
    db_settings = get_global_settings(db) # Ensures the configuration exists

    # Gets the data from the update schema, excluding unset values
    update_data = settings_update.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        # CORRECTED: The condition `and value is not None` has been removed.
        # This allows setting a field to `None` (clearing it), which is necessary
        # when the user selects "(Not Set)" in the UI.
        if hasattr(db_settings, key):
            setattr(db_settings, key, value)
            
    db.commit()
    db.refresh(db_settings)
    
    return db_settings


# NEW: Function to create an LLM evaluation run
def create_llm_evaluation_run(
    db: Session,
    evaluation_data: LLMEvaluationRunCreate,
    task_id: str
) -> LLMEvaluationRun:
    """
    Creates a new record for an LLM evaluation run in the database.
    """
    db_evaluation_run = LLMEvaluationRun(
        task_id=task_id,
        status='PENDING',
        llm_category=evaluation_data.llm_category,
        llm_server_url=evaluation_data.llm_server_url,
        llm_model_name=evaluation_data.llm_model_name,
        llm_context_window=evaluation_data.llm_context_window
    )
    db.add(db_evaluation_run)
    db.commit()
    db.refresh(db_evaluation_run)
    return db_evaluation_run


def get_llm_evaluation_runs_by_category(db: Session, llm_category: str) -> List[LLMEvaluationRunResult]:
    """
    Retrieves all LLM evaluation runs for a specific category,
    ordered by creation date descending.
    """
    return db.query(LLMEvaluationRun)\
                .filter(LLMEvaluationRun.llm_category == llm_category)\
                .order_by(LLMEvaluationRun.created_at.desc())\
                .all()