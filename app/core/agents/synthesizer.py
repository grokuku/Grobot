# app/core/agents/synthesizer.py
import json
import logging
from typing import List, Dict, Any

from app.core.agents.prompts import SYNTHESIZER_SYSTEM_PROMPT
from app.core.llm.ollama_client import get_llm_response_stream 
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


async def run_synthesizer(
    history: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    bot_personality: str,
    bot_name: str
) -> Any:
    """
    Runs the Synthesizer agent to generate the final, user-facing response as a stream.
    """
    logger.debug("Running Synthesizer to generate final response...")

    tool_results_prompt_section = _format_tool_results_for_prompt(tool_results)

    prompt = SYNTHESIZER_SYSTEM_PROMPT.strip()
    prompt = prompt.replace("{bot_name}", bot_name)
    prompt = prompt.replace("{bot_personality}", bot_personality)

    final_prompt_messages = list(history)
    final_prompt_messages.append({
        "role": "system",
        "content": tool_results_prompt_section
    })

    # === AJOUT POUR DEBUG: Logging du prompt final envoyé au LLM ===
    logger.info("================ SYNTHESIZER FINAL PROMPT ================")
    logger.info(f"System Prompt passed to LLM client:\n---\n{prompt}\n---")
    logger.info(f"Messages passed to LLM client:\n---\n{json.dumps(final_prompt_messages, indent=2)}\n---")
    logger.info("==========================================================")
    # === FIN DE L'AJOUT POUR DEBUG ===

    try:
        return get_llm_response_stream(
            system_prompt=prompt,
            messages=final_prompt_messages
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred in Synthesizer: {e}", exc_info=True)
        async def error_generator():
            yield "I'm sorry, I encountered an error while trying to formulate my response."
        return error_generator()