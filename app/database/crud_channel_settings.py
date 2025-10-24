# app/database/crud_channel_settings.py
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging

from . import sql_models
from ..schemas import bot_schemas

logger = logging.getLogger(__name__)

def get_channel_settings(db: Session, bot_id: int, channel_id: str) -> Optional[sql_models.ChannelSettings]:
    """
    Retrieves the specific settings for a given bot and channel.
    """
    return db.query(sql_models.ChannelSettings).filter_by(bot_id=bot_id, channel_id=channel_id).first()

def get_all_channel_settings_for_bot(db: Session, bot_id: int) -> List[sql_models.ChannelSettings]:
    """
    Retrieves all channel settings for a specific bot.
    """
    return db.query(sql_models.ChannelSettings).filter_by(bot_id=bot_id).all()

def upsert_channel_settings(
    db: Session,
    bot_id: int,
    channel_id: str,
    settings_data: bot_schemas.ChannelSettingsUpdate
) -> sql_models.ChannelSettings:
    """
    Creates or updates the settings for a specific bot and channel.
    'Upsert' logic is handled to simplify the API layer.
    """
    db_settings = get_channel_settings(db, bot_id=bot_id, channel_id=channel_id)
    
    if db_settings:
        # Update existing settings
        logger.info(f"Updating existing channel settings for bot {bot_id}, channel {channel_id}")
        update_data = settings_data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_settings, key, value)
    else:
        # Create new settings
        logger.info(f"Creating new channel settings for bot {bot_id}, channel {channel_id}")
        db_settings = sql_models.ChannelSettings(
            bot_id=bot_id,
            channel_id=channel_id,
            **settings_data.model_dump()
        )
        db.add(db_settings)
    
    try:
        db.commit()
        db.refresh(db_settings)
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error during upsert of channel settings: {e}")
        raise
        
    return db_settings