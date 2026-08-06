import asyncio
import json
import os
import uuid
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
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
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        try:
                            msg = json.loads(line)
                            self.nodes[msg["id"]] = msg
                            self.current_node_id = msg["id"]
                        except Exception:
                            pass

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
            with open(STATE_FILE, "a") as f:
                f.write(json.dumps(msg) + "\n")
        
        await asyncio.to_thread(_write)
        return msg_id

async def run_agent():
    state = AgentState()
    client = LLMClient()
    session = PromptSession()

    console.print("[bold green]Turtle Agent initialized (Fast CLI Mode)[/bold green]")
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
        
        await state.append_message("system", sys_prompt)

    input_queue = asyncio.Queue()

    async def input_loop():
        while True:
            try:
                with patch_stdout():
                    user_input = await session.prompt_async("turtle> ")
                if user_input.strip():
                    await input_queue.put(user_input)
            except (EOFError, KeyboardInterrupt):
                await input_queue.put("/exit")
                break

    async def process_loop():
        nonlocal client
        while True:
            user_input = await input_queue.get()
            
            # Slash Commands
            if user_input.startswith("/"):
                cmd = user_input.strip().split()[0].lower()
                if cmd == "/help":
                    console.print("[bold cyan]Available Commands:[/bold cyan]\n/help - Show this help\n/model - Switch model\n/tree - Show session tree\n/checkout <id> - Switch branch\n/undo - Go back one step\n/clear - Clear session history\n/compact - Summarize conversation to save context window\n/exit or /quit - Exit agent")
                    continue
                elif cmd == "/tree":
                    # Build and print a simple tree representation
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
                            
                    def print_tree(node_id, prefix=""):
                        n = state.nodes[node_id]
                        role = n.get("role", "")
                        content = str(n.get("content", ""))[:30].replace("\n", " ") + "..." if n.get("content") else ""
                        marker = "*" if node_id == state.current_node_id else " "
                        console.print(f"{prefix}{marker} [{node_id}] {role}: {content}")
                        
                        for i, child_id in enumerate(children.get(node_id, [])):
                            is_last = (i == len(children[node_id]) - 1)
                            new_prefix = prefix + ("└── " if is_last else "├── ")
                            next_prefix = prefix + ("    " if is_last else "│   ")
                            # print the child prefix, then pass next_prefix for its children
                            n_role = state.nodes[child_id].get("role", "")
                            n_content = str(state.nodes[child_id].get("content", ""))[:30].replace("\n", " ") + "..." if state.nodes[child_id].get("content") else ""
                            n_marker = "*" if child_id == state.current_node_id else " "
                            console.print(f"{new_prefix}{n_marker} [{child_id}] {n_role}: {n_content}")
                            for c in children.get(child_id, []):
                                _print_tree_recursive(c, next_prefix)

                    def _print_tree_recursive(node_id, prefix=""):
                        for i, child_id in enumerate(children.get(node_id, [])):
                            is_last = (i == len(children[node_id]) - 1)
                            new_prefix = prefix + ("└── " if is_last else "├── ")
                            next_prefix = prefix + ("    " if is_last else "│   ")
                            n_role = state.nodes[child_id].get("role", "")
                            n_content = str(state.nodes[child_id].get("content", ""))[:30].replace("\n", " ") + "..." if state.nodes[child_id].get("content") else ""
                            n_marker = "*" if child_id == state.current_node_id else " "
                            console.print(f"{new_prefix}{n_marker} [{child_id}] {n_role}: {n_content}")
                            for c in children.get(child_id, []):
                                _print_tree_recursive(c, next_prefix)

                    if not roots:
                        console.print("[yellow]Empty tree.[/yellow]")
                    else:
                        for root in roots:
                            print_tree(root)
                    continue
                elif cmd == "/checkout" or cmd == "/fork":
                    parts = user_input.strip().split()
                    if len(parts) < 2:
                        console.print("[bold red]Usage: /checkout <id>[/bold red]")
                        continue
                    target_id = parts[1]
                    if target_id not in state.nodes:
                        console.print(f"[bold red]Error: Node {target_id} not found.[/bold red]")
                    else:
                        state.current_node_id = target_id
                        console.print(f"[bold green]Switched to node {target_id}[/bold green]")
                    continue
                elif cmd == "/undo":
                    if state.current_node_id and state.nodes[state.current_node_id].get("parent_id"):
                        state.current_node_id = state.nodes[state.current_node_id]["parent_id"]
                        console.print(f"[bold green]Moved back to node {state.current_node_id}[/bold green]")
                    else:
                        console.print("[bold yellow]Already at root node.[/bold yellow]")
                    continue
                elif cmd == "/model":
                    parts = user_input.strip().split()
                    if len(parts) < 2:
                        console.print(f"[bold cyan]Current model:[/bold cyan] {client.provider}:{client.model}")
                        continue
                    
                    model_str = parts[1]
                    if ":" in model_str:
                        provider, model = model_str.split(":", 1)
                    else:
                        provider, model = "openai", model_str
                    
                    try:
                        new_client = LLMClient(provider=provider, model=model)
                        await client.close()
                        client = new_client
                        console.print(f"[bold green]Switched model to {provider}:{model}[/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Failed to switch model: {e}[/bold red]")
                    
                    continue
                elif cmd == "/clear":
                    state.nodes = {}
                    state.current_node_id = None
                    if os.path.exists(STATE_FILE):
                        os.remove(STATE_FILE)
                    console.print("[bold yellow]Session cleared. Restart agent to re-load context.[/bold yellow]")
                    continue
                elif cmd == "/compact":
                    lineage = state.get_lineage()
                    if len(lineage) <= 1:
                        console.print("[yellow]Not enough history to compact.[/yellow]")
                        continue
                    
                    console.print("[bold blue]Turtle is compacting history...[/bold blue]")
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
                                console.out(delta.content, end="")
                        console.out("\n")
                        
                        system_msg = lineage[0]
                        # Create a new assistant node summarizing context, appended directly to the system root node
                        # Temporarily change current_node_id to root to append summary branch
                        old_head = state.current_node_id
                        state.current_node_id = system_msg["id"]
                        
                        new_head = await state.append_message("assistant", content=f"## Context Checkpoint\n\n{summary}")
                        # Keep current_node_id pointing to the new compaction branch
                        state.current_node_id = new_head
                        
                        console.print("[bold green]History compacted successfully into new branch.[/bold green]")
                    except Exception as e:
                        console.print(f"[bold red]Compaction failed: {e}[/bold red]")
                        state.current_node_id = old_head
                    continue
                elif cmd in ("/exit", "/quit"):
                    os._exit(0)
                else:
                    console.print(f"[bold red]Unknown command: {cmd}[/bold red]")
                    continue

            await state.append_message("user", user_input)
            
            while True:
                assistant_content = ""
                current_tool_calls = {}
                console.print("[bold blue]Turtle:[/bold blue] ", end="")
                
                interrupted = False
                try:
                    async for chunk in client.stream_chat(state.get_messages(), tools=TOOLS_SCHEMA):
                        if not input_queue.empty():
                            console.print("\n[bold yellow]Interrupting generation for steering message...[/bold yellow]")
                            interrupted = True
                            break
                            
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        
                        if delta.content:
                            assistant_content += delta.content
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

                console.out("") # Newline
                
                tool_calls_list = list(current_tool_calls.values()) if current_tool_calls else None
                await state.append_message("assistant", content=assistant_content or None, tool_calls=tool_calls_list)
                
                if interrupted:
                    break
                
                if tool_calls_list:
                    for tc in tool_calls_list:
                        if not input_queue.empty():
                            console.print("\n[bold yellow]Interrupting tools for steering message...[/bold yellow]")
                            interrupted = True
                            break
                            
                        name = tc["function"]["name"]
                        arguments = tc["function"]["arguments"]
                        console.print(f"[dim]Executing tool: {name}({arguments})[/dim]")
                        
                        result = await execute_tool(name, arguments)
                        result_str = str(result)
                        display_result = result_str[:200] + "..." if len(result_str) > 200 else result_str
                        console.print(f"[dim]Tool result: {display_result.strip()}[/dim]")
                        await state.append_message("tool", content=result_str, tool_call_id=tc["id"], name=name)
                    
                    if interrupted:
                        break
                    continue
                else:
                    break

    await asyncio.gather(input_loop(), process_loop())
    await client.close()

class Agent:
    """
    Headless Agent API for Antigravity JSON Hooks and MCP.
    """
    def __init__(self):
        self.state = AgentState()
        self.client = LLMClient()
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
        await self.state.append_message("system", sys_prompt)
        self._system_initialized = True

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

