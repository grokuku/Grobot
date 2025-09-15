# app/database/crud_settings.py

from sqlalchemy.orm import Session
from app.database.sql_models import GlobalSettings
from app.schemas.settings_schema import GlobalSettingsUpdate, GlobalSettings as GlobalSettingsSchema

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
        if hasattr(db_settings, key):
            setattr(db_settings, key, value)
            
    db.commit()
    db.refresh(db_settings)
    
    return db_settings