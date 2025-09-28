# /app/app/core/agents/parameter_extractor.py
import json
import logging
from typing import List, Dict, Any

from app.core.agents.prompts import PARAMETER_EXTRACTOR_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_json_response
from app.schemas.chat_schemas import ChatMessage, ParameterExtractorResult

logger = logging.getLogger(__name__)


def _format_required_tools_for_prompt(required_tools: List[Dict[str, Any]]) -> str:
    """
    Formats the required tools and their parameters into a string for the LLM.

    This provides the LLM with the "schema" of the information it needs to find.

    Args:
        required_tools: A list of full tool definitions for the tools
                        identified in the previous step.

    Returns:
        A formatted string describing the tools and their required parameters.
    """
    if not required_tools:
        return "No tools require parameter extraction."

    prompt = "You must find the parameters for the following tools:\n\n"
    for tool in required_tools:
        tool_name = tool.get("name", "N/A")
        prompt += f"- Tool: `{tool_name}`\n"
        
        input_schema = tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        
        if not properties:
            prompt += "  - This tool requires no parameters.\n"
            continue

        for param_name, param_details in properties.items():
            param_type = param_details.get("type", "any")
            param_desc = param_details.get("description", "No description.")
            prompt += f"  - Parameter: `{param_name}` (type: {param_type})\n    Description: {param_desc}\n"
    
    return prompt


async def run_parameter_extractor(
    history: List[ChatMessage],
    required_tools_definitions: List[Dict[str, Any]]
) -> ParameterExtractorResult:
    """
    Runs the Parameter Extractor agent to find arguments for required tools.

    Args:
        history: The conversation history.
        required_tools_definitions: The full MCP definitions for the required tools.

    Returns:
        A ParameterExtractorResult object detailing found and missing parameters,
        and a clarification question if needed. Returns an empty result on failure.
    """
    logger.debug("Running Parameter Extractor...")

    if not required_tools_definitions:
        logger.info("No tools were identified, skipping parameter extraction.")
        return ParameterExtractorResult()

    # 1. Format the required tools schema into a string for the prompt.
    tools_schema_prompt_section = _format_required_tools_for_prompt(required_tools_definitions)

    # 2. Combine the base prompt with the dynamic tool schema section.
    system_prompt = PARAMETER_EXTRACTOR_SYSTEM_PROMPT + "\n\n" + tools_schema_prompt_section

    messages = [msg.model_dump() for msg in history]

    try:
        # 3. Call the LLM.
        llm_response_str = await get_llm_json_response(
            system_prompt=system_prompt,
            messages=messages
        )

        # === AJOUT DU LOGGING DÉTAILLÉ ===
        logger.info(f"Raw JSON response from Parameter Extractor LLM: {llm_response_str}")
        # ==================================

        # 4. Parse and validate the response.
        result_data = json.loads(llm_response_str)
        result = ParameterExtractorResult.model_validate(result_data)

        if result.missing_parameters:
            logger.info(f"Parameter Extractor found missing parameters and generated clarification: {result.clarification_question}")
        else:
            logger.info("Parameter Extractor found all required parameters.")

        return result

    except json.JSONDecodeError:
        logger.error("Parameter Extractor failed to parse LLM response as JSON.")
        return ParameterExtractorResult() # Safe default
    except Exception as e:
        logger.error(f"An unexpected error occurred in Parameter Extractor: {e}", exc_info=True)
        return ParameterExtractorResult() # Safe default