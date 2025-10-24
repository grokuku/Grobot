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
    This version now correctly handles text and image content types.
    """
    if not tool_results:
        return "No tools were executed."

    prompt = "Here are the results from the tools that were executed:\n\n"
    for res in tool_results:
        tool_name = res.get("tool_name", "unknown_tool")
        result_data = res.get("result", {})
        
        # Handle potential error messages first
        if isinstance(result_data, dict) and "error" in result_data:
            error_message = result_data["error"]
            if isinstance(error_message, dict):
                error_message = error_message.get("message", "Unknown error")
            prompt += f"--- Tool: `{tool_name}` ---\nResult: The tool execution failed with an error: {error_message}\n\n"
            continue

        content_list = result_data.get("content", [])
        formatted_outputs = []

        if not content_list:
            tool_output = "The tool returned no content."
        else:
            for item in content_list:
                item_type = item.get("type")
                if item_type == "text":
                    formatted_outputs.append(item.get("text", ""))
                elif item_type == "image":
                    source_url = item.get("source")
                    if source_url:
                        # Create a clear, structured sentence for the LLM to parse.
                        formatted_outputs.append(f"An image was generated and is available at the following URL: {source_url}")
            
            if not formatted_outputs:
                tool_output = "The tool returned content but it could not be displayed (unsupported type)."
            else:
                tool_output = " ".join(formatted_outputs)

        prompt += f"--- Tool: `{tool_name}` ---\nResult: {tool_output}\n\n"
    
    return prompt

# MODIFIED: The function signature and logic are completely updated
async def run_synthesizer(
    bot: Bot,
    global_settings: GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]] # Kept for signature consistency, but ignored
) -> AsyncGenerator[str, None]:
    """
    Runs the conversational Synthesizer agent for scenarios where NO tools were used.
    """
    logger.debug("Running conversational Synthesizer to generate response...")

    try:
        # 1. Resolve LLM config for 'Output Client'
        output_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT
        )

        # 2. Prepare prompts and messages for conversation
        system_prompt = llm_manager.prompts.SYNTHESIZER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            bot_personality=bot.personality
        )

        logger.info(f"Conversational Synthesizer calling LLM with config: {output_config.model_dump()}")

        # 3. Use the llm_manager to get a streamed response
        async for chunk in llm_manager.call_llm_stream(
            config=output_config,
            system_prompt=system_prompt,
            messages=list(history) # Only history is needed
        ):
            yield chunk

    except Exception as e:
        logger.error(f"An unexpected error in conversational Synthesizer: {e}", exc_info=True)
        yield "I'm sorry, I encountered an error while trying to formulate my response."


async def run_tool_result_synthesizer(
    bot: Bot,
    global_settings: GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]]
) -> AsyncGenerator[str, None]:
    """
    Runs the Tool Result Synthesizer agent to report tool execution results to the user.
    """
    logger.debug("Running Tool Result Synthesizer to report tool outputs...")

    try:
        # 1. Resolve LLM config for 'Output Client'
        output_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT
        )

        # 2. Prepare prompts and messages using the specialized prompt
        tool_results_prompt_section = _format_tool_results_for_prompt(tool_results)
        system_prompt = llm_manager.prompts.TOOL_RESULT_SYNTHESIZER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            bot_personality=bot.personality
        )

        final_prompt_messages = list(history)
        final_prompt_messages.append({
            "role": "system",
            "content": tool_results_prompt_section
        })

        logger.info(f"Tool Result Synthesizer calling LLM with config: {output_config.model_dump()}")

        # 3. Use the llm_manager to get a streamed response
        async for chunk in llm_manager.call_llm_stream(
            config=output_config,
            system_prompt=system_prompt,
            messages=final_prompt_messages
        ):
            yield chunk

    except Exception as e:
        logger.error(f"An unexpected error in Tool Result Synthesizer: {e}", exc_info=True)
        yield "I'm sorry, I encountered an error while trying to report the results."