#### app/core/agents/tool_identifier.py
import json
import logging
from typing import List, Dict, Any

from app.core.agents.prompts import TOOL_IDENTIFIER_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_json_response
from app.schemas.chat_schemas import ChatMessage, ToolIdentifierResult

logger = logging.getLogger(__name__)


def _format_tools_for_prompt(available_tools: List[Dict[str, Any]]) -> str:
    """
    Formats the list of available tools into a simple string for the LLM prompt.

    This helps the LLM understand what tools it can choose from by showing
    only the most essential information: name and description.

    Args:
        available_tools: A list of tool definitions from MCP servers.

    Returns:
        A formatted string describing the available tools.
    """
    if not available_tools:
        return "No tools are available for use."

    formatted_string = ""
    for tool in available_tools:
        name = tool.get("name", "N/A")
        description = tool.get("description", "No description available.")
        formatted_string += f'- `{name}`: {description}\n'
    return formatted_string


async def run_tool_identifier(
    history: List[ChatMessage],
    available_tools: List[Dict[str, Any]]
) -> ToolIdentifierResult:
    """
    Runs the Tool Identifier agent to determine which tools are needed for a request.

    Args:
        history: The conversation history.
        available_tools: A list of tool definitions (from MCP servers).

    Returns:
        A ToolIdentifierResult object containing the list of required tool names.
        Returns an empty list in case of any failure.
    """
    logger.debug("Running Tool Identifier...")

    # 1. Format the available tools into a string to be injected into the prompt.
    tools_prompt_section = _format_tools_for_prompt(available_tools)

    # 2. Inject the formatted tool list into the system prompt template.
    system_prompt = TOOL_IDENTIFIER_SYSTEM_PROMPT.replace(
        "{{available_tools}}", tools_prompt_section
    )
    
    # --- MODIFICATION: Passage du log en INFO pour garantir sa visibilité ---
    logger.info(f"Final system prompt for Tool Identifier:\n{system_prompt}")

    messages = [msg.model_dump() for msg in history]

    try:
        # 3. Call the LLM with the combined prompt and conversation history.
        llm_response_str = await get_llm_json_response(
            system_prompt=system_prompt,
            messages=messages
        )

        # 4. Parse the LLM's JSON response.
        result_data = json.loads(llm_response_str)

        # 5. Validate the data against our Pydantic schema.
        result = ToolIdentifierResult.model_validate(result_data)

        if result.required_tools:
            logger.info(f"Tool Identifier identified required tools: {result.required_tools}")
        else:
            logger.info("Tool Identifier concluded that no tools are required.")

        return result

    except json.JSONDecodeError:
        logger.error("Tool Identifier failed to parse LLM response as JSON.")
        return ToolIdentifierResult()  # Return default empty list
    except Exception as e:
        logger.error(f"An unexpected error occurred in Tool Identifier: {e}", exc_info=True)
        return ToolIdentifierResult()  # Return default empty list