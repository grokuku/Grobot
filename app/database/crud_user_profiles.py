from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_
from app.database import sql_models
from app.schemas import user_profile_schemas
import logging # NOUVEAU: Import du module de logging

def get_user_profile(db: Session, bot_id: int, user_id: str, server_id: str) -> sql_models.UserProfile | None:
    """
    Retrieves a specific user profile based on the composite key of bot, user, and server.

    Args:
        db: The database session.
        bot_id: The ID of the bot.
        user_id: The Discord ID of the user.
        server_id: The Discord ID of the server.

    Returns:
        The UserProfile object if found, otherwise None.
    """
    return db.query(sql_models.UserProfile).filter(
        sql_models.UserProfile.bot_id == bot_id,
        sql_models.UserProfile.discord_user_id == user_id,
        sql_models.UserProfile.server_discord_id == server_id
    ).first()

# MODIFIÉ: La fonction gère maintenant la création et la mise à jour des noms d'utilisateur.
def get_or_create_user_profile(
    db: Session, 
    bot_id: int, 
    user_id: str, 
    server_id: str, 
    username: str | None = None, 
    display_name: str | None = None
) -> sql_models.UserProfile:
    """
    Retrieves a user profile, creating it if it doesn't exist.
    It also automatically updates the username and display_name if they are provided and have changed.

    Args:
        db: The database session.
        bot_id: The ID of the bot.
        user_id: The Discord ID of the user.
        server_id: The Discord ID of the server.
        username: The user's current Discord username (e.g., 'johndoe').
        display_name: The user's current display name on the server (e.g., 'John D.').

    Returns:
        The existing or newly created and up-to-date UserProfile object.
    """
    db_profile = get_user_profile(db, bot_id=bot_id, user_id=user_id, server_id=server_id)
    
    if not db_profile:
        # Profile doesn't exist, create it with all available info.
        # This relies on the UserProfileCreate schema accepting these new fields.
        profile_data = user_profile_schemas.UserProfileCreate(
            bot_id=bot_id,
            discord_user_id=user_id,
            server_discord_id=server_id,
            username=username,
            display_name=display_name
        )
        db_profile = create_user_profile(db, profile=profile_data)
    else:
        # Profile exists, check if an update is needed to keep names fresh.
        needs_update = False
        if username and db_profile.username != username:
            db_profile.username = username
            needs_update = True
        
        if display_name and db_profile.display_name != display_name:
            db_profile.display_name = display_name
            needs_update = True
            
        if needs_update:
            db.commit()
            db.refresh(db_profile)
            
    return db_profile

def create_user_profile(db: Session, profile: user_profile_schemas.UserProfileCreate) -> sql_models.UserProfile:
    """
    Creates a new user profile in the database.

    Args:
        db: The database session.
        profile: The Pydantic schema containing the profile data.

    Returns:
        The newly created UserProfile object.
    """
    db_profile = sql_models.UserProfile(**profile.model_dump())
    db.add(db_profile)
    db.commit()
    db.refresh(db_profile)
    return db_profile

def update_user_profile(db: Session, bot_id: int, user_id: str, server_id: str, profile_update: user_profile_schemas.UserProfileUpdate) -> sql_models.UserProfile | None:
    """
    Updates an existing user profile's behavioral instructions.

    Args:
        db: The database session.
        bot_id: The ID of the bot.
        user_id: The Discord ID of the user.
        server_id: The Discord ID of the server.
        profile_update: A schema with the fields to update.

    Returns:
        The updated UserProfile object, or None if not found.
    """
    db_profile = get_user_profile(db, bot_id=bot_id, user_id=user_id, server_id=server_id)
    if db_profile:
        update_data = profile_update.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_profile, key, value)
        db.commit()
        db.refresh(db_profile)
    return db_profile

# MODIFIÉ: Ajout de .distinct() pour éviter de retourner des profils en double.
def search_users_globally(db: Session, query: str):
    """
    Searches for users across all bots and servers by display name, username, or Discord ID.
    Returns a list of matching profiles, fully loaded with their associated bots.
    """
    search_term = f"%{query}%"
    
    # Build the filter conditions dynamically
    filters = [
        sql_models.UserProfile.display_name.ilike(search_term),
        sql_models.UserProfile.username.ilike(search_term)
    ]

    # Only add the user ID comparison if the query is a valid integer
    if query.isdigit():
        filters.append(sql_models.UserProfile.discord_user_id == query)

    # Find all profiles matching any of the conditions
    profiles = db.query(sql_models.UserProfile).options(
        joinedload(sql_models.UserProfile.bot)
    ).filter(
        or_(*filters)
    ).distinct().all()
    
    return profiles

# MODIFIÉ: La logique de recherche est maintenant plus stricte et correcte.
def search_users_in_bot(db: Session, bot_id: int, query: str) -> list[sql_models.UserProfile]:
    """
    Searches for users within a specific bot's context by display name, username, or Discord ID.
    If the query is numeric, it only performs an exact match on the user ID.
    Otherwise, it performs a case-insensitive search on name fields.

    Args:
        db: The database session.
        bot_id: The ID of the bot to search within.
        query: The search term (display name, username, or Discord ID).

    Returns:
        A list of matching UserProfile objects for the given bot.
    """
    logging.warning(f"CRUD_LOG: search_users_in_bot received call with bot_id='{bot_id}', query='{query}'")

    # If the query is empty or just whitespace, return all users for the bot.
    if not query or not query.strip():
        logging.warning("CRUD_LOG: Query is empty, returning all users for bot.")
        return get_user_profiles_by_bot(db, bot_id=bot_id)

    # CORRECTION: Sépare la logique de recherche pour les IDs et pour le texte.
    if query.isdigit():
        # If the query is a number, search for an exact match on the Discord ID only.
        logging.warning("CRUD_LOG: Query is a digit. Searching by exact discord_user_id.")
        user_filters = [sql_models.UserProfile.discord_user_id == query]
    else:
        # Otherwise, perform a case-insensitive search on text fields.
        logging.warning("CRUD_LOG: Query is text. Searching by name/display_name.")
        search_term = f"%{query}%"
        user_filters = [
            sql_models.UserProfile.display_name.ilike(search_term),
            sql_models.UserProfile.username.ilike(search_term)
        ]

    profiles = db.query(sql_models.UserProfile).filter(
        and_(
            sql_models.UserProfile.bot_id == bot_id,
            or_(*user_filters)
        )
    ).all()
    
    logging.warning(f"CRUD_LOG: Database query returned {len(profiles)} result(s).")
    return profiles

# NOUVEAU: Ajout de la fonction pour lister les profils par bot.
def get_user_profiles_by_bot(db: Session, bot_id: int) -> list[sql_models.UserProfile]:
    """
    Retrieves all user profiles associated with a specific bot.

    Args:
        db: The database session.
        bot_id: The ID of the bot.

    Returns:
        A list of UserProfile objects for the given bot.
    """
    return db.query(sql_models.UserProfile).filter(sql_models.UserProfile.bot_id == bot_id).all()