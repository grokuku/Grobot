import json
import logging
from typing import List

from app.core.agents.prompts import ARCHIVIST_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_json_response
from app.schemas.chat_schemas import ChatMessage, ArchivistDecision

logger = logging.getLogger(__name__)


async def run_archivist(
    full_conversation: List[ChatMessage]
) -> ArchivistDecision:
    """
    Runs the Archivist agent to decide what information, if any, to save to long-term memory.

    This agent analyzes the full conversation and extracts factual statements
    about the user to be saved as notes.

    Args:
        full_conversation: The complete conversation history, including the user's
                            initial request and the bot's final synthesized answer.

    Returns:
        An ArchivistDecision object containing a list of notes to create.
        Returns an empty decision in case of any failure.
    """
    logger.debug("Running Archivist to analyze conversation for memory...")

    messages = [msg.model_dump() for msg in full_conversation]

    try:
        # 1. Call the LLM with the archivist prompt and the full conversation.
        llm_response_str = await get_llm_json_response(
            system_prompt=ARCHIVIST_SYSTEM_PROMPT,
            messages=messages
        )

        # 2. Parse the LLM's JSON response.
        decision_data = json.loads(llm_response_str)

        # 3. Validate the data against our Pydantic schema.
        decision = ArchivistDecision.model_validate(decision_data)

        if decision.notes_to_create:
            note_count = len(decision.notes_to_create)
            logger.info(f"Archivist decided to create {note_count} new user note(s).")
        else:
            logger.info("Archivist found no new information worth saving.")

        return decision

    except json.JSONDecodeError:
        logger.error("Archivist failed to parse LLM response as JSON.")
        return ArchivistDecision()  # Safe default
    except Exception as e:
        logger.error(f"An unexpected error occurred in Archivist: {e}", exc_info=True)
        return ArchivistDecision()  # Safe default