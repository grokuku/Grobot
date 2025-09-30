# app/core/agents/archivist.py
import json
import logging
from typing import List

# MODIFIED: Import the new LLM manager and necessary DB models
from app.core import llm_manager
from app.database.sql_models import Bot, GlobalSettings
from app.schemas.chat_schemas import ChatMessage, ArchivistDecision

logger = logging.getLogger(__name__)


async def run_archivist(
    bot: Bot,
    global_settings: GlobalSettings,
    full_conversation: List[ChatMessage]
) -> ArchivistDecision:
    """
    Runs the Archivist agent to decide what information to save to long-term memory.
    This version uses the llm_manager to resolve the correct LLM configuration.
    """
    logger.debug("Running Archivist to analyze conversation for memory...")

    messages = [msg.model_dump() for msg in full_conversation]

    try:
        # 1. Resolve the specific LLM config. 'Tools' is a good fit for structured data extraction.
        tools_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_TOOLS
        )
        
        # 2. Call the LLM using the manager. The prompt is already in the manager's scope.
        logger.info(f"Archivist calling LLM with config: {tools_config.model_dump()}")
        llm_response_str = await llm_manager.call_llm(
            config=tools_config,
            system_prompt=llm_manager.prompts.ARCHIVIST_SYSTEM_PROMPT,
            messages=messages,
            json_mode=True
        )

        # 3. Parse and validate the response.
        decision_data = json.loads(llm_response_str)
        decision = ArchivistDecision.model_validate(decision_data)

        if decision.notes_to_create:
            note_count = len(decision.notes_to_create)
            logger.info(f"Archivist decided to create {note_count} new user note(s).")
        else:
            logger.info("Archivist found no new information worth saving.")

        return decision

    except json.JSONDecodeError:
        logger.error("Archivist failed to parse LLM response as JSON.")
        return ArchivistDecision()
    except Exception as e:
        logger.error(f"An unexpected error occurred in Archivist: {e}", exc_info=True)
        return ArchivistDecision()