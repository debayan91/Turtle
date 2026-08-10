# Turtle Agent

**Turtle** is an ultra-fast, local-first CLI coding agent designed for seamless interaction with your codebase. Built with an interactive Terminal User Interface (TUI), Turtle brings a rich, responsive, and state-aware AI pair programming experience directly to your terminal.

Turtle is optimized for use with the **Antigravity** local proxy ecosystem, allowing lightning-fast model switching and robust local execution.

---

## Key Features

- **Blazing Fast TUI**: Built on top of `prompt_toolkit` and `rich`, Turtle offers a highly responsive, syntax-highlighted, and aesthetically pleasing terminal interface.
- **Native Antigravity Integration**: Connects effortlessly to your `localhost:3000` proxy server out-of-the-box.
- **Seamless Model Switching**: Dynamic autocomplete for all your local models. Type `/model ` and hit `<Tab>` to see available models and hot-swap them mid-session.
- **Non-Destructive Interrupts**: Safely abort long-running LLM generations or runaway bash commands by pressing `Escape` or `Ctrl+C`. Tool processes are cleanly terminated without leaving zombie processes.
- **State Tree Navigation**: Turtle maintains your conversation history as a state tree, allowing you to easily branch off alternative paths using `/checkout`, `/undo`, or `/tree`.
- **Advanced Agentic Capabilities**: Full suite of filesystem and execution tools (`read`, `write`, `edit`, `ls`, `find`, `grep`, and `bash`) enabling the agent to autonomously navigate and modify your project.

## Prerequisites

- Python 3.11 or higher
- The **Antigravity** local server running on `localhost:3000`

## Installation

It is recommended to run Turtle in an isolated Python virtual environment.

```bash
# 1. Clone the repository and navigate to the python project directory
cd turtle/turtle

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Turtle and its dependencies in editable mode
pip install -e .
```

## Usage

To launch the Turtle agent, simply run:

```bash
turtle
```

Alternatively, you can run it via the Python module:

```bash
python -m turtle_agent
```

Once the TUI loads, you can type your instructions directly into the prompt. The active model name is dynamically displayed in the footer.

### Keyboard Shortcuts
- **Enter**: Submit your prompt
- **Alt+Enter** (or **Escape, Enter**): Insert a newline in the input box
- **Escape** or **Ctrl+C** (when buffer is empty): Gracefully interrupt the current LLM stream or executing tool
- **Tab**: Auto-complete commands and model names

## Slash Commands

Turtle includes a variety of built-in commands for managing your session. These support autocomplete via `Tab`.

| Command | Description |
|---|---|
| `/models` | Fetches and displays a list of all currently available models from your local Antigravity server. |
| `/model <name>` | Instantly switches the active LLM engine to the specified model (e.g., `/model gemini-3.5-pro`). |
| `/tree` | Displays the current conversation state tree, showing the lineage of your chat history. |
| `/checkout <id>` | Switches the conversation context to a specific node ID in your state tree. |
| `/undo` | Steps back one node in your conversation history. |
| `/clear` | Wipes the current session state and clears the context history. |
| `/compact` | Condenses linear conversation histories into a single root node to save memory and context window limits. |
| `/help` | Displays usage instructions and a list of available commands. |
| `/exit` or `/quit` | Exits the Turtle agent safely. |

## Architecture Highlights

- **Streaming Parser**: Highly robust chunk accumulator capable of dynamically reconstructing fragmented JSON tool calls from edge-case model streams.
- **uvloop & httpx**: Asynchronous core leveraging `uvloop` for raw performance and HTTP/2 connections for minimized latency during local proxy communications.
- **Process Group Sandboxing**: Executed bash tools are wrapped in process groups (via `os.setsid`), ensuring that terminal interrupts properly kill any spawned child processes without leaving orphans.

---
*Built for the terminal, optimized for speed.*
