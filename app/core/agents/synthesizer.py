# app/core/agents/synthesizer.py
import json
import logging
from typing import List, Dict, Any, AsyncGenerator

from app.core import llm_manager
from app.database.sql_models import Bot, GlobalSettings
from app.schemas.chat_schemas import ChatMessage

logger = logging.getLogger(__name__)


def _format_tool_results_for_prompt(tool_results: List[Dict[str, Any]]) -> str:
    """
    Formats the results of the tool execution plan into a readable string for the LLM.
    Updated to support the standardized 'text_content' field from agent_orchestrator.
    """
    if not tool_results:
        return "No tools were executed."

    prompt = "Here are the results from the tools that were executed:\n\n"
    for res in tool_results:
        tool_name = res.get("tool_name", "unknown_tool")
        result_data = res.get("result", {})
        
        # 1. Handle explicit errors
        if isinstance(result_data, dict) and "error" in result_data:
            error_message = result_data["error"]
            if isinstance(error_message, dict):
                error_message = error_message.get("message", "Unknown error")
            prompt += f"--- Tool: `{tool_name}` ---\nResult: The tool execution failed with an error: {error_message}\n\n"
            continue

        tool_output = ""

        # 2. Check for the standardized 'text_content' (New Orchestrator Format)
        if isinstance(result_data, dict) and "text_content" in result_data:
            tool_output = result_data["text_content"]
        
        # 3. Fallback: Check for 'content' list (Legacy/Raw MCP Format)
        elif isinstance(result_data, dict) and "content" in result_data:
            content_list = result_data.get("content", [])
            formatted_outputs = []
            
            for item in content_list:
                # Handle dicts or objects
                item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
                
                if item_type == "text":
                    text_val = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                    formatted_outputs.append(text_val)
                elif item_type == "image":
                    # Handle image source/url
                    if isinstance(item, dict):
                            source_url = item.get("source") or item.get("url") # Try common keys
                            mime_type = item.get("mimeType")
                    else:
                            source_url = getattr(item, "source", None) or getattr(item, "url", None)
                            mime_type = getattr(item, "mimeType", None)

                    if source_url:
                        formatted_outputs.append(f"An image was generated and is available at the following URL: {source_url}")
                    elif mime_type:
                        formatted_outputs.append(f"[Image Data: {mime_type}]")

            if formatted_outputs:
                tool_output = " ".join(formatted_outputs)
            else:
                    # If content list exists but is empty or unparsable
                    tool_output = "The tool executed but returned no displayable content."

        # 4. Last Resort: Dump the whole result
        else:
            tool_output = str(result_data)

        prompt += f"--- Tool: `{tool_name}` ---\nResult: {tool_output}\n\n"
    
    return prompt

async def run_synthesizer(
    bot: Bot,
    global_settings: GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]], 
    playbook_content: str = "",
    current_time: str = ""  # ADDED: current_time parameter
) -> AsyncGenerator[str, None]:
    """
    Runs the conversational Synthesizer agent for scenarios where NO tools were used.
    """
    logger.debug("Running conversational Synthesizer to generate response...")

    try:
        output_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT
        )

        # Updated format call with current_time
        system_prompt = llm_manager.prompts.SYNTHESIZER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            bot_personality=bot.personality,
            ace_playbook=playbook_content,
            current_time=current_time
        )

        logger.info(f"Conversational Synthesizer calling LLM with config: {output_config.model_dump()}")

        async for chunk in llm_manager.call_llm_stream(
            config=output_config,
            system_prompt=system_prompt,
            messages=list(history)
        ):
            yield chunk

    except Exception as e:
        logger.error(f"An unexpected error in conversational Synthesizer: {e}", exc_info=True)
        yield "I'm sorry, I encountered an error while trying to formulate my response."


async def run_tool_result_synthesizer(
    bot: Bot,
    global_settings: GlobalSettings,
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    playbook_content: str = "",
    current_time: str = ""  # ADDED: current_time parameter
) -> AsyncGenerator[str, None]:
    """
    Runs the Tool Result Synthesizer agent to report tool execution results to the user.
    """
    logger.debug("Running Tool Result Synthesizer to report tool outputs...")

    try:
        output_config = llm_manager.resolve_llm_config(
            bot, global_settings, llm_manager.LLM_CATEGORY_OUTPUT_CLIENT
        )

        # Format the results using the improved function
        tool_results_prompt_section = _format_tool_results_for_prompt(tool_results)
        
        # Updated format call with current_time
        system_prompt = llm_manager.prompts.TOOL_RESULT_SYNTHESIZER_SYSTEM_PROMPT.format(
            bot_name=bot.name,
            bot_personality=bot.personality,
            ace_playbook=playbook_content,
            current_time=current_time
        )

        final_prompt_messages = list(history)
        final_prompt_messages.append({
            "role": "system",
            "content": tool_results_prompt_section
        })

        logger.info(f"Tool Result Synthesizer calling LLM with config: {output_config.model_dump()}")

        async for chunk in llm_manager.call_llm_stream(
            config=output_config,
            system_prompt=system_prompt,
            messages=final_prompt_messages
        ):
            yield chunk

    except Exception as e:
        logger.error(f"An unexpected error in Tool Result Synthesizer: {e}", exc_info=True)
        yield "I'm sorry, I encountered an error while trying to report the results."