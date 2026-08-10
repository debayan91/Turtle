import asyncio
import json
import logging
from typing import Callable, Awaitable, Optional
from .workspace import WorkspaceState
from .llm import LLMClient
from ..tools.registry import TOOLS_SCHEMA, execute_tool

log = logging.getLogger(__name__)

MAX_TOOL_RETRIES = 3
MAX_AGENT_ITERATIONS = 20  # prevent infinite loops


async def run_agent_turn(
    state: WorkspaceState,
    client: LLMClient,
    prompt: str,
    yield_text_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    yield_tool_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
) -> str:
    """
    Run one user turn through the agent loop.

    - Streams LLM text chunks via `yield_text_callback(text)`.
    - Notifies about tool execution via `yield_tool_callback(name, status)`
      where status is "ok" or "error".
    - Self-heals: on tool error, injects the error into context and lets the
      LLM retry up to MAX_TOOL_RETRIES times.
    - Terminates after MAX_AGENT_ITERATIONS to prevent runaway loops.
    """
    await state.append_message("user", prompt)

    final_response = ""
    iterations = 0

    while iterations < MAX_AGENT_ITERATIONS:
        iterations += 1
        assistant_content = ""
        current_tool_calls: dict = {}

        # ── Stream LLM response ────────────────────────────────────────────────
        try:
            async for chunk in client.stream_chat(state.get_messages(), tools=TOOLS_SCHEMA):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    assistant_content += delta.content
                    if yield_text_callback:
                        await yield_text_callback(delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in current_tool_calls:
                            current_tool_calls[idx] = {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name or "", "arguments": ""},
                            }
                        if tc.function and tc.function.arguments:
                            current_tool_calls[idx]["function"]["arguments"] += tc.function.arguments

        except Exception as e:
            err = f"\n[LLM Stream Error]: {e}"
            if yield_text_callback:
                await yield_text_callback(err)
            # Store partial assistant message and abort
            await state.append_message("assistant", content=assistant_content + err or None)
            break

        tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None

        # Persist assistant message
        await state.append_message(
            "assistant",
            content=assistant_content or None,
            tool_calls=tool_calls_list,
        )

        if assistant_content:
            final_response += assistant_content + "\n"

        if not tool_calls_list:
            # No tool calls → turn is done
            break

        # ── Execute tools ──────────────────────────────────────────────────────
        for tc in tool_calls_list:
            name = tc["function"]["name"]
            arguments = tc["function"]["arguments"]

            success = False
            for attempt in range(MAX_TOOL_RETRIES):
                try:
                    result = await execute_tool(name, arguments)
                    await state.append_message(
                        "tool", content=str(result),
                        tool_call_id=tc["id"], name=name,
                    )
                    if yield_tool_callback:
                        await yield_tool_callback(name, "ok")
                    success = True
                    break
                except Exception as e:
                    err_msg = str(e)
                    is_last = (attempt == MAX_TOOL_RETRIES - 1)
                    if is_last:
                        await state.append_message(
                            "tool",
                            content=f"Fatal error after {MAX_TOOL_RETRIES} attempts: {err_msg}",
                            tool_call_id=tc["id"], name=name,
                        )
                        if yield_tool_callback:
                            await yield_tool_callback(name, "error")
                    else:
                        # Self-heal: inject error so LLM can course-correct
                        await state.append_message(
                            "tool",
                            content=f"Error: {err_msg}. Fix your arguments and retry.",
                            tool_call_id=tc["id"], name=name,
                        )
                        if yield_tool_callback:
                            await yield_tool_callback(name, "error")

        # Loop back to let LLM process tool results

    if iterations >= MAX_AGENT_ITERATIONS:
        log.warning("Agent hit MAX_AGENT_ITERATIONS (%d) for prompt: %s…", MAX_AGENT_ITERATIONS, prompt[:80])
        if yield_text_callback:
            await yield_text_callback("\n[Agent hit iteration limit — stopping.]\n")

    return final_response.strip()
