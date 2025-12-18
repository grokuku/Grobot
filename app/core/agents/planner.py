# /app/app/core/agents/planner.py
import json
import logging
from typing import List, Dict, Any

from app.core.agents.prompts import PLANNER_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_json_response
from app.schemas.chat_schemas import ChatMessage, PlannerResult, ParameterExtractorResult

logger = logging.getLogger(__name__)


def _format_validated_tools_for_prompt(validated_params: ParameterExtractorResult) -> str:
    """
    Formats the validated tools and their parameters into a string for the Planner.

    This gives the LLM a clear list of the building blocks it can use to construct the plan.

    Args:
        validated_params: The result from the Parameter Extractor, confirming
                            all necessary parameters have been found.

    Returns:
        A formatted string describing the tools and parameters available for planning.
    """
    if not validated_params.extracted_parameters:
        return "No tools and parameters are available to build a plan."

    prompt = "You have the following tools and their parameters fully validated. Create an execution plan based on them:\n\n"
    for tool_name, args in validated_params.extracted_parameters.items():
        prompt += f"- Tool: `{tool_name}`\n"
        if args:
            for arg_name, arg_value in args.items():
                prompt += f"  - Argument: `{arg_name}` = `{arg_value}`\n"
        else:
            prompt += "  - This tool takes no arguments.\n"
    
    return prompt


async def run_planner(
    history: List[ChatMessage],
    validated_parameters: ParameterExtractorResult,
    playbook_content: str = ""
) -> PlannerResult:
    """
    Runs the Planner agent to create a step-by-step execution plan.

    Args:
        history: The conversation history, for overall context.
        validated_parameters: The output from the Parameter Extractor, confirming
                                all parameters are available.
        playbook_content: The ACE playbook content as a formatted string.

    Returns:
        A PlannerResult object containing the ordered execution plan.
        Returns an empty plan in case of failure.
    """
    logger.debug("Running Planner...")

    if not validated_parameters.extracted_parameters:
        logger.info("No validated parameters available, skipping planner.")
        return PlannerResult()

    # 1. Format the validated tools and params into a string for the prompt.
    available_blocks_prompt = _format_validated_tools_for_prompt(validated_parameters)

    # 2. Combine the base prompt with the dynamic section.
    # INJECTION OF ACE PLAYBOOK
    base_prompt = PLANNER_SYSTEM_PROMPT.format(ace_playbook=playbook_content)
    system_prompt = base_prompt + "\n\n" + available_blocks_prompt

    messages = [msg.model_dump() for msg in history]

    try:
        # 3. Call the LLM.
        llm_response_str = await get_llm_json_response(
            system_prompt=system_prompt,
            messages=messages
        )

        # 4. Parse and validate the response against our Pydantic schema.
        result_data = json.loads(llm_response_str)
        plan = PlannerResult.model_validate(result_data)

        if plan.plan:
            logger.info(f"Planner created a plan with {len(plan.plan)} step(s).")
        else:
            logger.warning("Planner generated an empty plan.")
        
        return plan

    except json.JSONDecodeError:
        logger.error("Planner failed to parse LLM response as JSON.")
        return PlannerResult() # Safe default
    except Exception as e:
        logger.error(f"An unexpected error occurred in Planner: {e}", exc_info=True)
        return PlannerResult() # Safe default