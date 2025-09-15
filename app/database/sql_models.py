# Fichier: app/database/sql_models.py
from sqlalchemy import (
    Column, Integer, String, JSON, DateTime, ForeignKey, Text, Boolean,
    BigInteger, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.associationproxy import association_proxy
from app.database.base import Base


class GlobalSettings(Base):
    """
    Model to store the application's global settings.
    This table is designed to contain only one row.
    """
    __tablename__ = "global_settings"

    id = Column(Integer, primary_key=True, default=1)

    # --- Global LLM Settings ---
    ollama_host_url = Column(String, default="http://host.docker.internal:11434")
    default_llm_model = Column(String, nullable=False, default="llama3")
    multimodal_llm_model = Column(String, nullable=False, default="llava")

    # --- Image Generation Service Settings ---
    image_generation_provider = Column(String, nullable=True, default="comfyui")
    image_generation_api_url = Column(String, nullable=True, default="http://host.docker.internal:8188")


    # --- Global Default System Prompts ---
    context_header_default_prompt = Column(
        Text,
        nullable=False,
        default=(
            '[IF context_type == "DIRECT_MESSAGE"]\n'
            'You are in a private conversation with the user \'{user_display_name}\' (username: @{user_name}).\n'
            '[/IF]'
            '[IF context_type == "SERVER_CHANNEL"]\n'
            'This conversation is in the server \'{server_name}\', in the channel \'#{channel_name}\'.\n'
            'The latest message is from \'{user_display_name}\' (username: @{user_name}).\n'
            '[/IF]'
            '[IF channel_is_thread == True]\n'
            'The current discussion is inside a thread named \'{thread_name}\'.\n'
            '[/IF]'
        )
    )
    tools_system_prompt = Column(
        Text,
        nullable=False,
        default=(
            "You have access to a set of tools you can use to answer the user's question.\n"
            "You must call tools by producing a JSON object with a `tool_calls` field.\n"
            "The `tool_calls` field must be a list of objects, where each object has a `function` field.\n"
            "The `function` object must have a `name` and an `arguments` field. The `arguments` field must be a JSON object with the arguments to the function.\n"
            "If you need to call a tool, you must stop generating text and produce the JSON object.\n"
            "If you don't need to call a tool, you must answer the user's question directly."
        )
    )

class BotMCPServerAssociation(Base):
    __tablename__ = "bot_mcp_server_association"
    bot_id = Column(Integer, ForeignKey("bots.id"), primary_key=True)
    mcp_server_id = Column(Integer, ForeignKey("mcp_servers.id"), primary_key=True)
    configuration = Column(JSON, nullable=True, default=dict)

    mcp_server = relationship("MCPServer", back_populates="bot_associations")
    bot = relationship("Bot", back_populates="mcp_server_associations")


class Bot(Base):
    """
    Model representing a configurable bot.
    """
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    discord_token = Column(String, unique=True, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    passive_listening_enabled = Column(Boolean, default=False, nullable=False)
    gatekeeper_history_limit = Column(Integer, nullable=False, server_default='5')
    conversation_history_limit = Column(Integer, nullable=False, server_default='15')
    system_prompt = Column(Text, default="You are a helpful AI assistant.", nullable=False)

    llm_provider = Column(String, default="ollama")
    llm_model = Column(String, nullable=True)
    use_custom_ollama = Column(Boolean, default=False, nullable=False)
    custom_ollama_host_url = Column(String, nullable=True)
    llm_context_window = Column(Integer, nullable=True)
    image_generation_settings = Column(JSON, nullable=True)
    settings = Column(JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    user_profiles = relationship("UserProfile", back_populates="bot", cascade="all, delete-orphan")
    # SUPPRIMÉ: L'ancienne relation directe vers UserNote est retirée.
    uploaded_files = relationship("UploadedFile", back_populates="bot", cascade="all, delete-orphan")

    mcp_server_associations = relationship(
        "BotMCPServerAssociation",
        back_populates="bot",
        cascade="all, delete-orphan"
    )

    mcp_servers = association_proxy(
        "mcp_server_associations", "mcp_server"
    )


class UserProfile(Base):
    """
    Stores admin-defined, high-level behavioral instructions for a bot
    regarding a specific user on a specific server.
    """
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    discord_user_id = Column(String, nullable=False, index=True)
    server_discord_id = Column(String, nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False, index=True)

    # --- NOUVEAUX CHAMPS AJOUTÉS ---
    display_name = Column(String, nullable=False, server_default="Unknown User", index=True)
    username = Column(String, nullable=False, server_default="unknown_user", index=True)

    behavioral_instructions = Column(Text, nullable=False, server_default="Interact with the user normally.")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    bot = relationship("Bot", back_populates="user_profiles")

    # NOUVEAU: Relation vers les notes pour un chargement facile.
    notes = relationship("UserNote", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('discord_user_id', 'server_discord_id', 'bot_id', name='_user_server_bot_uc'),
    )


class UserNote(Base):
    """
    Stores a single, factual note about a user, learned by a bot.
    Includes a reliability score estimated by the LLM.
    """
    __tablename__ = "user_notes"

    id = Column(Integer, primary_key=True, index=True)
    
    # CORRIGÉ: Remplacé les IDs redondants par une clé étrangère directe vers UserProfile.
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False, index=True)
    
    author_discord_id = Column(String, nullable=False, index=True)

    note_content = Column(Text, nullable=False)
    reliability_score = Column(Integer, nullable=False, server_default='50')

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # CORRIGÉ: La note est maintenant liée au profil, pas directement au bot.
    profile = relationship("UserProfile", back_populates="notes")

    __table_args__ = (
        CheckConstraint('reliability_score >= 0 AND reliability_score <= 100', name='reliability_score_check'),
    )


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id = Column(Integer, primary_key=True)
    uuid = Column(String, unique=True, nullable=False, index=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    owner_discord_id = Column(String, nullable=False, index=True)
    access_level = Column(String, nullable=False, default='PRIVATE')
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_family = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    file_metadata = Column(postgresql.JSONB, nullable=True)
    storage_path = Column(String, nullable=False)
    storage_status = Column(String, nullable=False, default='PRESENT')
    description = Column(Text, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    bot = relationship("Bot", back_populates="uploaded_files")


class MCPServer(Base):
    """
    Model representing a standalone MCP (Model Context Protocol) tool server.
    """
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    rpc_endpoint_path = Column(String, nullable=False, server_default="/mcp")
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    bot_associations = relationship(
        "BotMCPServerAssociation",
        back_populates="mcp_server",
        cascade="all, delete-orphan"
    )

    bots = association_proxy(
        "bot_associations", "bot"
    )