import asyncio
import json
import os
import uuid
from rich.console import Console
import re

from turtle.tui import TurtleTUI
import re

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

def discover_skills() -> str:
    skills = []
    skill_roots = [
        os.path.expanduser("~/.gemini/config/skills"),
        os.path.join(os.getcwd(), ".agents", "skills"),
        os.path.join(os.getcwd(), ".pi", "skills")
    ]
    
    for root_dir in skill_roots:
        if not os.path.exists(root_dir):
            continue
        for dirpath, _, filenames in os.walk(root_dir):
            for filename in filenames:
                if filename == "SKILL.md":
                    full_path = os.path.join(dirpath, filename)
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            
                        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
                        if match:
                            frontmatter = match.group(1)
                            name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
                            desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
                            
                            name = name_match.group(1).strip() if name_match else os.path.basename(dirpath)
                            description = desc_match.group(1).strip() if desc_match else ""
                            
                            if description:
                                skills.append({
                                    "name": name,
                                    "description": description,
                                    "location": full_path
                                })
                    except Exception:
                        pass
    
    if not skills:
        return ""
        
    lines = [
        "\n\nThe following skills provide specialized instructions for specific tasks.",
        "Use the bash_command tool to execute `cat <location>` to load a skill's file when the task matches its description.",
        "When a skill file references a relative path, resolve it against the skill directory (parent of SKILL.md) and use that absolute path in tool commands.",
        "",
        "<available_skills>"
    ]
    
    for skill in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{skill['name']}</name>")
        lines.append(f"    <description>{skill['description']}</description>")
        lines.append(f"    <location>{skill['location']}</location>")
        lines.append("  </skill>")
    
    lines.append("</available_skills>")
    return "\n".join(lines)

class AgentState:
    def __init__(self):
        self.nodes = {}
        self.current_node_id = None
        self.load_warnings = []
        self._load_state()

    def get_lock(self):
        if not hasattr(self, '_lock'):
            self._lock = asyncio.Lock()
        return self._lock

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            corrupt = False
            with open(STATE_FILE, "r") as f:
                for line_idx, line in enumerate(f):
                    if line.strip():
                        try:
                            msg = json.loads(line)
                            self.nodes[msg["id"]] = msg
                            self.current_node_id = msg["id"]
                        except json.JSONDecodeError:
                            self.load_warnings.append(f"Warning: Corrupt line {line_idx+1} in {STATE_FILE}.")
                            corrupt = True
                        except Exception as e:
                            self.load_warnings.append(f"Error loading state: {e}")
            if corrupt:
                self.load_warnings.append(f"Warning: {STATE_FILE} contains corrupted lines. The agent will ignore them but continue.")

    def get_messages(self, head_id=None) -> list:
        current = head_id or self.current_node_id
        messages = []
        while current:
            msg = self.nodes.get(current)
            if not msg:
                break
            
            # Filter out id and parent_id when passing to LLM
            clean_msg = {k: v for k, v in msg.items() if k not in ("id", "parent_id")}
            messages.append(clean_msg)
            current = msg.get("parent_id")
        return messages[::-1]

    def get_lineage(self, head_id=None) -> list:
        current = head_id or self.current_node_id
        nodes = []
        while current:
            msg = self.nodes.get(current)
            if not msg:
                break
            nodes.append(msg)
            current = msg.get("parent_id")
        return nodes[::-1]

    async def append_message(self, role: str, content: str | None = None, tool_calls: list = None, tool_call_id: str = None, name: str = None) -> str:
        msg_id = uuid.uuid4().hex[:8]
        msg = {
            "id": msg_id,
            "parent_id": self.current_node_id,
            "role": role
        }
        if content is not None:
            msg["content"] = content
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if name is not None:
            msg["name"] = name

        self.nodes[msg_id] = msg
        self.current_node_id = msg_id
        
        # Append to file in a separate thread to avoid blocking the async event loop
        def _write():
            try:
                with open(STATE_FILE, "a") as f:
                    f.write(json.dumps(msg) + "\n")
            except OSError as e:
                # If we fail to write state, we log to stdout. 
                # This ensures the process loop doesn't crash entirely on a disk-full error, 
                # though it means state won't persist.
                print(f"\n[!] WARNING: Failed to write to {STATE_FILE}: {e}")
        
        async with self.get_lock():
            await asyncio.to_thread(_write)
        return msg_id

async def run_agent():
    state = AgentState()
    try:
        client = LLMClient()
    except ValueError:
        client = LLMClient(provider="antigravity", model="gemini-3.5-pro")
    input_queue = asyncio.Queue()
    interrupt_event = asyncio.Event()

    def _exit_cb():
        pass  # Rely on app.exit() to stop the TUI cleanly
        
    def _interrupt_cb():
        interrupt_event.set()

    tui = TurtleTUI(input_queue=input_queue, exit_callback=_exit_cb, interrupt_callback=_interrupt_cb)

    def update_ui_footer():
        tui.layout_engine.update_footer(f"<b>Turtle</b> | Model: <style bg='ansiblack' fg='ansigreen'>{client.model}</style> | Use <style bg='ansiyellow' fg='ansiblack'>Shift+Enter</style> for newline, <style bg='ansiyellow' fg='ansiblack'>Ctrl+C</style> to exit")

    update_ui_footer()

    async def init_models():
        models = await client.get_models()
        if models:
            tui.layout_engine.update_completer(models)
            tui.app.invalidate()
    
    asyncio.create_task(init_models())

    tui.append_transcript("[bold green]Turtle Agent initialized (Fast TUI Mode)[/bold green]")
    if not state.nodes:
        sys_prompt = "You are Turtle, an ultra-fast local CLI coding agent. You can use the provided tools to interact with the file system and execute commands.\n"
        
        # Context Ingestion
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
        
        # Skills Discovery & Injection
        sys_prompt += discover_skills()
        
        if state.load_warnings:
            sys_prompt += "\n\n--- System Warnings ---\n" + "\n".join(state.load_warnings)
        
        await state.append_message("system", sys_prompt)

    async def process_loop():
        nonlocal client
        while True:
            try:
                interrupt_event.clear()
                user_input = await input_queue.get()
                
                # Slash Commands
                if user_input.startswith("/"):
                    cmd = user_input.strip().split()[0].lower()
                    if cmd == "/help":
                        tui.append_transcript("[bold cyan]Available Commands:[/bold cyan]\n/help - Show this help\n/models - List available models\n/model - Switch model\n/tree - Show session tree\n/checkout <id> - Switch branch\n/undo - Go back one step\n/clear - Clear session history\n/compact - Summarize conversation to save context window\n/exit or /quit - Exit agent")
                        continue
                    elif cmd == "/tree":
                        children = {}
                        roots = []
                        for nid, n in state.nodes.items():
                            pid = n.get("parent_id")
                            if not pid:
                                roots.append(nid)
                            else:
                                if pid not in children:
                                    children[pid] = []
                                children[pid].append(nid)
                                
                        def _get_tree_str(node_id, prefix=""):
                            n = state.nodes[node_id]
                            role = n.get("role", "")
                            content = str(n.get("content", ""))[:30].replace("\n", " ") + "..." if n.get("content") else ""
                            marker = "*" if node_id == state.current_node_id else " "
                            result = f"{prefix}{marker} [{node_id}] {role}: {content}\n"
                            
                            for i, child_id in enumerate(children.get(node_id, [])):
                                is_last = (i == len(children[node_id]) - 1)
                                new_prefix = prefix + ("└── " if is_last else "├── ")
                                next_prefix = prefix + ("    " if is_last else "│   ")
                                n_role = state.nodes[child_id].get("role", "")
                                n_content = str(state.nodes[child_id].get("content", ""))[:30].replace("\n", " ") + "..." if state.nodes[child_id].get("content") else ""
                                n_marker = "*" if child_id == state.current_node_id else " "
                                result += f"{new_prefix}{n_marker} [{child_id}] {n_role}: {n_content}\n"
                                for c in children.get(child_id, []):
                                    result += _print_tree_recursive(c, next_prefix)
                            return result

                        def _print_tree_recursive(node_id, prefix=""):
                            result = ""
                            for i, child_id in enumerate(children.get(node_id, [])):
                                is_last = (i == len(children[node_id]) - 1)
                                new_prefix = prefix + ("└── " if is_last else "├── ")
                                next_prefix = prefix + ("    " if is_last else "│   ")
                                n_role = state.nodes[child_id].get("role", "")
                                n_content = str(state.nodes[child_id].get("content", ""))[:30].replace("\n", " ") + "..." if state.nodes[child_id].get("content") else ""
                                n_marker = "*" if child_id == state.current_node_id else " "
                                result += f"{new_prefix}{n_marker} [{child_id}] {n_role}: {n_content}\n"
                                for c in children.get(child_id, []):
                                    result += _print_tree_recursive(c, next_prefix)
                            return result

                        if not roots:
                            tui.append_transcript("[yellow]Empty tree.[/yellow]")
                        else:
                            tree_output = ""
                            for root in roots:
                                tree_output += _get_tree_str(root)
                            tui.append_transcript(tree_output)
                        continue
                    elif cmd == "/checkout" or cmd == "/fork":
                        parts = user_input.strip().split()
                        if len(parts) < 2:
                            tui.append_transcript("[bold red]Usage: /checkout <id>[/bold red]")
                            continue
                        target_id = parts[1]
                        if target_id not in state.nodes:
                            tui.append_transcript(f"[bold red]Error: Node {target_id} not found.[/bold red]")
                        else:
                            state.current_node_id = target_id
                            tui.append_transcript(f"[bold green]Switched to node {target_id}[/bold green]")
                        continue
                    elif cmd == "/undo":
                        if state.current_node_id and state.nodes[state.current_node_id].get("parent_id"):
                            state.current_node_id = state.nodes[state.current_node_id]["parent_id"]
                            tui.append_transcript(f"[bold green]Moved back to node {state.current_node_id}[/bold green]")
                        else:
                            tui.append_transcript("[bold yellow]Already at root node.[/bold yellow]")
                        continue
                    elif cmd == "/models":
                        tui.append_transcript("[bold cyan]Fetching available models...[/bold cyan]")
                        models = await client.get_models()
                        if models:
                            model_list = "\n".join([f" - [bold green]{m}[/bold green]" for m in models])
                            tui.append_transcript(f"[bold cyan]Available Antigravity Models:[/bold cyan]\n{model_list}")
                            tui.layout_engine.update_completer(models)
                        else:
                            tui.append_transcript("[bold red]No models found. Check if the local server is running.[/bold red]")
                        continue
                    elif cmd == "/model":
                        parts = user_input.strip().split()
                        if len(parts) < 2:
                            tui.append_transcript(f"[bold cyan]Current model:[/bold cyan] {client.model}")
                            continue
                        
                        new_model = parts[1]
                        try:
                            # Re-initialize the client with the new model but same provider (antigravity)
                            new_client = LLMClient(provider=client.provider, model=new_model, api_key=client.api_key, base_url=client.base_url)
                            await client.close()
                            client = new_client
                            update_ui_footer()
                            tui.append_transcript(f"[bold green]Switched model to {new_model}[/bold green]")
                        except Exception as e:
                            tui.display_error(f"Failed to switch model: {e}")
                        
                        continue
                    elif cmd == "/clear":
                        state.nodes = {}
                        state.current_node_id = None
                        async with state.get_lock():
                            if os.path.exists(STATE_FILE):
                                os.remove(STATE_FILE)
                        tui.append_transcript("[bold yellow]Session cleared. Restart agent to re-load context.[/bold yellow]")
                        continue
                    elif cmd == "/compact":
                        lineage = state.get_lineage()
                        if len(lineage) <= 1:
                            tui.append_transcript("[yellow]Not enough history to compact.[/yellow]")
                            continue
                        
                        tui.append_transcript("[bold blue]Turtle is compacting history...[/bold blue]")
                        history_text = ""
                        for msg in lineage[1:]:
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
                            
                            system_msg = lineage[0]
                            old_head = state.current_node_id
                            state.current_node_id = system_msg["id"]
                            
                            new_head = await state.append_message("assistant", content=f"## Context Checkpoint\n\n{summary}")
                            state.current_node_id = new_head
                            
                            tui.append_transcript("[bold green]History compacted successfully into new branch.[/bold green]")
                        except Exception as e:
                            tui.display_error(f"Compaction failed: {e}")
                            state.current_node_id = old_head
                        continue
                    elif cmd in ("/exit", "/quit"):
                        tui.app.exit()
                        break
                    else:
                        tui.append_transcript(f"[bold red]Unknown command: {cmd}[/bold red]")
                        continue

                await state.append_message("user", user_input)
                tui.append_transcript(f"\n[bold blue]You:[/bold blue] {user_input}")
                
                while True:
                    assistant_content = ""
                    current_tool_calls = {}
                    tui.append_transcript("[bold blue]Turtle is thinking...[/bold blue]")
                    
                    interrupted = False
                    try:
                        async for chunk in client.stream_chat(state.get_messages(), tools=TOOLS_SCHEMA):
                            if interrupt_event.is_set():
                                tui.append_transcript("\n[bold yellow]Agent generation interrupted by user.[/bold yellow]")
                                interrupted = True
                                interrupt_event.clear()
                                current_tool_calls = {}
                                break
                                
                            if not input_queue.empty():
                                tui.append_transcript("\n[bold yellow]Interrupting generation for steering message...[/bold yellow]")
                                interrupted = True
                                break
                                
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            
                            if delta.content:
                                assistant_content += delta.content
                                # In a real implementation we would stream to the UI, 
                                # but appending complete lines or chunks is safer.
                            
                            if delta.tool_calls:
                                for tc in delta.tool_calls:
                                    if tc.index not in current_tool_calls:
                                        current_tool_calls[tc.index] = {
                                            "id": tc.id,
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""}
                                        }
                                    
                                    if tc.function:
                                        if tc.function.name:
                                            current_tool_calls[tc.index]["function"]["name"] += tc.function.name
                                        if tc.function.arguments:
                                            current_tool_calls[tc.index]["function"]["arguments"] += tc.function.arguments
                    except Exception as e:
                        tui.display_error(f"Error during generation: {e}")
                        current_tool_calls = {}  # Discard incomplete tool calls
                        break

                    if assistant_content:
                        tui.append_transcript(f"[bold blue]Turtle:[/bold blue]\n{assistant_content}")
                    
                    tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None
                    await state.append_message("assistant", content=assistant_content or None, tool_calls=tool_calls_list)
                    
                    if interrupted:
                        break
                    
                    if tool_calls_list:
                        for tc in tool_calls_list:
                            if interrupt_event.is_set():
                                tui.append_transcript("\n[bold yellow]Tool execution queue interrupted by user.[/bold yellow]")
                                interrupted = True
                                interrupt_event.clear()
                                break
                                
                            if not input_queue.empty():
                                tui.append_transcript("\n[bold yellow]Interrupting tools for steering message...[/bold yellow]")
                                interrupted = True
                                break
                                
                            name = tc["function"]["name"]
                            arguments = tc["function"]["arguments"]
                            tui.append_transcript(f"[dim]Executing tool: {name}({arguments})[/dim]")
                            
                            try:
                                tool_task = asyncio.create_task(execute_tool(name, arguments))
                                interrupt_task = asyncio.create_task(interrupt_event.wait())
                                
                                done, pending = await asyncio.wait(
                                    [tool_task, interrupt_task],
                                    return_when=asyncio.FIRST_COMPLETED
                                )
                                
                                if interrupt_task in done:
                                    tool_task.cancel()
                                    tui.append_transcript("\n[bold yellow]Tool execution aborted![/bold yellow]")
                                    err_msg = f"Tool {name} aborted by user interrupt."
                                    await state.append_message("tool", content=err_msg, tool_call_id=tc["id"], name=name)
                                    interrupted = True
                                    interrupt_event.clear()
                                    
                                    # Wait for cancellation to complete safely without raising
                                    try:
                                        await tool_task
                                    except asyncio.CancelledError:
                                        pass
                                    break
                                else:
                                    interrupt_task.cancel()
                                    result = tool_task.result()
                                    result_str = str(result)
                                    display_result = result_str[:200] + "..." if len(result_str) > 200 else result_str
                                    tui.append_transcript(f"[dim]Tool result: {display_result.strip()}[/dim]")
                                    await state.append_message("tool", content=result_str, tool_call_id=tc["id"], name=name)
                            except Exception as e:
                                err_msg = f"Tool {name} failed: {e}"
                                tui.display_error(err_msg)
                                await state.append_message("tool", content=err_msg, tool_call_id=tc["id"], name=name)
                        
                        if interrupted:
                            break
                        continue
                    else:
                        break
                        
            except Exception as e:
                tui.display_error(f"Fatal error in process loop: {e}")
                # We do not break, allowing the UI to remain alive

    try:
        tui_task = asyncio.create_task(tui.run_async())
        process_task = asyncio.create_task(process_loop())
        
        done, pending = await asyncio.wait(
            [tui_task, process_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for task in pending:
            task.cancel()
    finally:
        await client.close()

class Agent:
    """
    Headless Agent API for Antigravity JSON Hooks and MCP.
    """
    def __init__(self):
        self.state = AgentState()
        try:
            self.client = LLMClient()
        except ValueError:
            self.client = LLMClient(provider="antigravity", model="gemini-3.5-pro")
        self._system_initialized = bool(self.state.nodes)
        
    async def _initialize_system_prompt(self):
        sys_prompt = "You are Turtle, an ultra-fast local CLI coding agent. You can use the provided tools to interact with the file system and execute commands.\n"
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
        sys_prompt += discover_skills()
        
        if self.state.load_warnings:
            sys_prompt += "\n\n--- System Warnings ---\n" + "\n".join(self.state.load_warnings)
            
        await self.state.append_message("system", sys_prompt)
        self._system_initialized = True
        
    async def close(self):
        if self.client:
            await self.client.close()

    async def run_single_turn(self, prompt: str) -> str:
        if not self._system_initialized:
            await self._initialize_system_prompt()
            
        await self.state.append_message("user", prompt)
        
        final_response = ""
        while True:
            assistant_content = ""
            current_tool_calls = {}
            
            try:
                async for chunk in self.client.stream_chat(self.state.get_messages(), tools=TOOLS_SCHEMA):
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    
                    if delta.content:
                        assistant_content += delta.content
                    
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
                assistant_content += f"\nError during generation: {e}"
                current_tool_calls = {}  # Discard incomplete tool calls
                break
            
            tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None
            await self.state.append_message("assistant", content=assistant_content or None, tool_calls=tool_calls_list)
            
            if assistant_content:
                final_response += assistant_content + "\n"
            
            if tool_calls_list:
                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    arguments = tc["function"]["arguments"]
                    result = await execute_tool(name, arguments)
                    await self.state.append_message("tool", content=str(result), tool_call_id=tc["id"], name=name)
                continue
            else:
                break
                
        return final_response.strip()

