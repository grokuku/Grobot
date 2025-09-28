import json
import logging
from typing import List

from app.core.agents.prompts import GATEKEEPER_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_json_response
from app.schemas.chat_schemas import ChatMessage, GatekeeperDecision

logger = logging.getLogger(__name__)


async def run_gatekeeper(
    bot_name: str,
    history: List[ChatMessage]
) -> GatekeeperDecision:
    """
    Runs the Gatekeeper agent to decide if the bot should respond to a message.

    This agent uses a specialized prompt to ask the LLM for a JSON-formatted
    decision, which is then validated against the GatekeeperDecision schema.

    Args:
        bot_name: The name of the bot, to be injected into the prompt.
        history: The recent conversation history.

    Returns:
        A GatekeeperDecision object containing the verdict and the reasoning.
        In case of any failure (e.g., invalid JSON from LLM), it defaults
        to a safe "do not respond" decision.
    """
    logger.debug(f"Running Gatekeeper for bot '{bot_name}'...")

    # 1. Format the system prompt with the specific bot's name.
    formatted_prompt = GATEKEEPER_SYSTEM_PROMPT.replace("{{bot_name}}", bot_name)

    # 2. Convert Pydantic models to dictionaries for the LLM client.
    messages = [msg.model_dump() for msg in history]

    try:
        # 3. Call the LLM with the specific prompt and messages.
        # We expect the ollama_client to handle the call and return a raw string.
        llm_response_str = await get_llm_json_response(
            system_prompt=formatted_prompt,
            messages=messages
        )

        # 4. Parse the LLM's string response into a Python dictionary.
        decision_data = json.loads(llm_response_str)

        # 5. Validate the dictionary against our Pydantic schema.
        # This ensures the LLM's output has the correct structure and types.
        decision = GatekeeperDecision.model_validate(decision_data)
        logger.info(f"Gatekeeper decision: {decision.should_respond}. Reason: {decision.reason}")
        return decision

    except json.JSONDecodeError:
        logger.error("Gatekeeper failed to parse LLM response as JSON.")
        # Fallback to a safe default if the LLM response is not valid JSON.
        return GatekeeperDecision(reason="LLM response was not valid JSON.", should_respond=False)
    except Exception as e:
        logger.error(f"An unexpected error occurred in Gatekeeper: {e}", exc_info=True)
        # Fallback to a safe default for any other unexpected errors.
        return GatekeeperDecision(reason=f"An unexpected error occurred: {str(e)}", should_respond=False)