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

SUMMARIZATION_SYSTEM_PROMPT = """You are a context summarization assistant. Your task is to read a conversation between a user and an AI assistant, then produce a structured summary following the exact format specified.

Do NOT continue the conversation. Do NOT respond to any questions in the conversation. ONLY output the structured summary."""

SUMMARIZATION_PROMPT = """The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages."""
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
        sys_prompt = "You are Turtle, an ultra-fast local CLI coding agent. You can use bash_command to execute tools.\n"
        
        # Context Ingestion
        # Scan common context file locations
        context_paths = ["AGENTS.md", ".pi/prompts"]
        for c_path in context_paths:
            if os.path.exists(c_path):
                if os.path.isdir(c_path):
                    for root, _, files in os.walk(c_path):
                        for file in files:
                            if file.endswith(".md"):
                                fpath = os.path.join(root, file)
                                try:
                                    with open(fpath, "r", encoding="utf-8") as f:
                                        sys_prompt += f"\n--- Context from {fpath} ---\n{f.read()}\n"
                                except Exception:
                                    pass
                else:
                    try:
                        with open(c_path, "r", encoding="utf-8") as f:
                            sys_prompt += f"\n--- Context from {c_path} ---\n{f.read()}\n"
                    except Exception:
                        pass
        
        await state.append_message("system", sys_prompt)

    while True:
        try:
            with patch_stdout():
                user_input = await session.prompt_async("turtle> ")
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input.strip():
            continue

        # Slash Commands
        if user_input.startswith("/"):
            cmd = user_input.strip().split()[0].lower()
            if cmd == "/help":
                console.print("[bold cyan]Available Commands:[/bold cyan]\n/help - Show this help\n/clear - Clear session history\n/compact - Summarize conversation to save context window\n/exit or /quit - Exit agent")
                continue
            elif cmd == "/clear":
                state.messages = []
                if os.path.exists(STATE_FILE):
                    os.remove(STATE_FILE)
                # Re-initialize system prompt
                console.print("[bold yellow]Session cleared. Restart agent to re-load context.[/bold yellow]")
                continue
            elif cmd == "/compact":
                if len(state.messages) <= 1:
                    console.print("[yellow]Not enough history to compact.[/yellow]")
                    continue
                
                console.print("[bold blue]Turtle is compacting history...[/bold blue]")
                
                # Serialize history to plain text for the LLM
                history_text = ""
                for msg in state.messages[1:]:
                    role = msg.get("role", "unknown")
                    content = msg.get("content", "")
                    if msg.get("tool_calls"):
                        content += f" [Tool Calls: {json.dumps(msg['tool_calls'])}]"
                    history_text += f"<{role}>\n{content}\n</{role}>\n\n"
                
                prompt_text = f"<conversation>\n{history_text}</conversation>\n\n{SUMMARIZATION_PROMPT}"
                
                summarization_messages = [
                    {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_text}
                ]
                
                summary = ""
                try:
                    async for chunk in client.stream_chat(summarization_messages):
                        if not chunk.choices: continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            summary += delta.content
                            console.out(delta.content, end="")
                    console.out("\n")
                    
                    # Retain the original system prompt, discard the rest, append the new context checkpoint summary
                    system_msg = state.messages[0]
                    state.messages = [system_msg, {"role": "assistant", "content": f"## Context Checkpoint\n\n{summary}"}]
                    
                    # Fully rewrite the state JSONL file
                    if os.path.exists(STATE_FILE):
                        os.remove(STATE_FILE)
                    for m in state.messages:
                        with open(STATE_FILE, "a") as f:
                            f.write(json.dumps(m) + "\n")
                            
                    console.print("[bold green]History compacted successfully.[/bold green]")
                except Exception as e:
                    console.print(f"[bold red]Compaction failed: {e}[/bold red]")
                
                continue
            elif cmd in ("/exit", "/quit"):
                break
            else:
                console.print(f"[bold red]Unknown command: {cmd}[/bold red]")
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
