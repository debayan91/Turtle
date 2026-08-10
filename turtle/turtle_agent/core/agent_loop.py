import asyncio
import json
import logging
from typing import Callable, Awaitable, Dict, Any, List
from .workspace import WorkspaceState
from .llm import LLMClient
from ..tools.registry import TOOLS_SCHEMA, execute_tool

log = logging.getLogger(__name__)

async def run_agent_turn(
    state: WorkspaceState,
    client: LLMClient,
    prompt: str,
    yield_callback: Callable[[str], Awaitable[None]] = None
) -> str:
    """
    Runs a single turn of the agent, executing tools and self-healing if needed.
    """
    await state.append_message("user", prompt)
    
    final_response = ""
    max_retries = 3
    
    while True:
        assistant_content = ""
        current_tool_calls = {}
        
        try:
            async for chunk in client.stream_chat(state.get_messages(), tools=TOOLS_SCHEMA):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                if delta.content:
                    assistant_content += delta.content
                    if yield_callback:
                        await yield_callback(delta.content)
                
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index not in current_tool_calls:
                            current_tool_calls[tc.index] = {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name or "", "arguments": ""}
                            }
                        if tc.function and tc.function.arguments:
                            current_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
        except Exception as e:
            err = f"\n[LLM Stream Error]: {e}"
            assistant_content += err
            if yield_callback:
                await yield_callback(err)
            current_tool_calls = {}
            break
        
        tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None
        await state.append_message("assistant", content=assistant_content or None, tool_calls=tool_calls_list)
        
        if assistant_content:
            final_response += assistant_content + "\n"
        
        if tool_calls_list:
            for tc in tool_calls_list:
                name = tc["function"]["name"]
                arguments = tc["function"]["arguments"]
                
                # Self-healing retry loop for tool execution
                for attempt in range(max_retries):
                    try:
                        result = await execute_tool(name, arguments)
                        await state.append_message("tool", content=str(result), tool_call_id=tc["id"], name=name)
                        if yield_callback:
                            await yield_callback(f"\n[Tool {name} executed successfully]\n")
                        break # Success, break out of retry loop
                    except Exception as e:
                        err_msg = str(e)
                        # If this was the last attempt, bubble up the failure
                        if attempt == max_retries - 1:
                            await state.append_message("tool", content=f"Fatal Tool Error after {max_retries} attempts: {err_msg}", tool_call_id=tc["id"], name=name)
                            if yield_callback:
                                await yield_callback(f"\n[Tool {name} failed permanently: {err_msg}]\n")
                        else:
                            # Self-healing: Provide the error to the LLM and prompt it to fix it
                            if yield_callback:
                                await yield_callback(f"\n[Tool {name} failed: {err_msg}. Retrying...]\n")
                            # We mock a tool response indicating the failure, so the LLM sees it immediately on the next generation
                            await state.append_message("tool", content=f"Error executing tool: {err_msg}. Please fix your arguments and try again.", tool_call_id=tc["id"], name=name)
                            break # Break the retry loop here to let the outer LLM loop generate a new call
                
            continue # Continue outer while loop to let LLM respond to tool results
        else:
            break
            
    return final_response.strip()
