import asyncio
import json
import os
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from turtle.llm import LLMClient
from turtle.tools import TOOLS_SCHEMA, execute_tool

STATE_FILE = "state.jsonl"
console = Console()

class AgentState:
    def __init__(self):
        self.messages = []
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        self.messages.append(json.loads(line))

    async def append_message(self, role: str, content: str | None = None, tool_calls: list = None, tool_call_id: str = None, name: str = None):
        msg = {"role": role}
        if content is not None:
            msg["content"] = content
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if name is not None:
            msg["name"] = name

        self.messages.append(msg)
        
        # Append to file in a separate thread to avoid blocking the async event loop
        def _write():
            with open(STATE_FILE, "a") as f:
                f.write(json.dumps(msg) + "\n")
        
        await asyncio.to_thread(_write)

async def run_agent():
    state = AgentState()
    client = LLMClient()
    session = PromptSession()

    console.print("[bold green]Turtle Agent initialized (Fast CLI Mode)[/bold green]")
    if not state.messages:
        await state.append_message("system", "You are Turtle, an ultra-fast local CLI coding agent. You can use bash_command to execute tools.")

    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async("turtle> ")
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input.strip():
            continue

        await state.append_message("user", user_input)
        
        while True:
            # Accumulate the assistant message
            assistant_content = ""
            current_tool_calls = {} # map index to tool call dict
            
            console.print("[bold blue]Turtle:[/bold blue] ", end="")
            
            # Use raw printing for instant feedback without rich overhead until block ends
            try:
                async for chunk in client.stream_chat(state.messages, tools=TOOLS_SCHEMA):
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    
                    if delta.content:
                        assistant_content += delta.content
                        # Instant terminal write
                        console.out(delta.content, end="")
                    
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            if tc.index not in current_tool_calls:
                                current_tool_calls[tc.index] = {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {"name": tc.function.name, "arguments": ""}
                                }
                            if tc.function and tc.function.arguments:
                                current_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
            except Exception as e:
                console.print(f"\n[red]Error during generation: {e}[/red]")
                break

            console.out("") # Newline after streaming
            
            # Append assistant message
            tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None
            await state.append_message("assistant", content=assistant_content or None, tool_calls=tool_calls_list)
            
            if tool_calls_list:
                # Execute tools
                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    arguments = tc["function"]["arguments"]
                    console.print(f"[dim]Executing tool: {name}({arguments})[/dim]")
                    
                    result = await execute_tool(name, arguments)
                    
                    result_str = str(result)
                    display_result = result_str[:200] + "..." if len(result_str) > 200 else result_str
                    console.print(f"[dim]Tool result: {display_result.strip()}[/dim]")
                    await state.append_message("tool", content=result_str, tool_call_id=tc["id"], name=name)
                
                # Loop back to let the LLM process the tool results
                continue
            else:
                break
                
    await client.close()
