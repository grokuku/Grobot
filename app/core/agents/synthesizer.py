# app/core/agents/synthesizer.py
import json
import logging
from typing import List, Dict, Any, AsyncGenerator

# MODIFIED: Import the new LLM manager and necessary DB models
from app.core import llm_manager
from app.database.sql_models import Bot, GlobalSettings
from app.schemas.chat_schemas import ChatMessage

logger = logging.getLogger(__name__)


def _format_tool_results_for_prompt(tool_results: List[Dict[str, Any]]) -> str:
    """
    Formats the results of the tool execution plan into a readable string for the LLM.
    """
    if not tool_results:
        return "No tools were executed."

    prompt = "Here are the results from the tools that were executed:\n\n"
    for res in tool_results:
        tool_name = res.get("tool_name", "unknown_tool")
        
        result_data = res.get("result", {})
        content_list = result_data.get("content", [])
        
        if not content_list:
            tool_output = "The tool returned no content."
        else:
            tool_output = " ".join([item.get("text", "") for item in content_list if item.get("type") == "text"])

        prompt += f"--- Tool: `{tool_name}` ---\nResult: {tool_output}\n\n"
    
    return prompt

# MODIFIED: The function signature and logic are completely updated
async def run_synthesizer(
    bot: Bot,
    global_settings: GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Runs the Synthesizer agent to generate the final, user-facing response as a stream.
    This version uses the llm_manager to resolve the correct LLM configuration.
    """
    logger.debug("Running Synthesizer to generate final response...")

    try:
        # 1. Resolve the specific LLM config for the 'Output Client' category
        output_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT
        )

        # 2. Prepare prompts and messages
        tool_results_prompt_section = _format_tool_results_for_prompt(tool_results)
        system_prompt = llm_manager.prompts.SYNTHESIZER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            bot_personality=bot.personality
        )

        final_prompt_messages = list(history)
        final_prompt_messages.append({
            "role": "system",
            "content": tool_results_prompt_section
        })

        logger.info(f"Synthesizer calling LLM with config: {output_config.model_dump()}")

        # 3. Use the llm_manager to get a streamed response
        # (Note: We need a new stream-specific function in llm_manager)
        async for chunk in llm_manager.call_llm_stream(
            config=output_config,
            system_prompt=system_prompt,
            messages=final_prompt_messages
        ):
            yield chunk

    except Exception as e:
        logger.error(f"An unexpected error occurred in Synthesizer: {e}", exc_info=True)
        yield "I'm sorry, I encountered an error while trying to formulate my response."