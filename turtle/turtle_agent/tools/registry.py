import json
from .fs import handle_read, handle_write, handle_ls, handle_find, handle_grep
from .edit import handle_edit
from .bash import execute_bash

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Reads a file's content. Use offset and limit for large files to read specific sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)"},
                    "limit": {"type": "integer", "description": "Maximum number of lines to read"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create a new file or overwrite an existing one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "content": {"type": "string", "description": "Content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replaces specific text within a file. targetContent must exactly match the existing file content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the file"},
                    "targetContent": {"type": "string", "description": "The exact string to be replaced, including whitespace and indentation"},
                    "replacementContent": {"type": "string", "description": "The content to replace targetContent with"},
                    "startLine": {"type": "integer", "description": "The starting line number of the chunk (1-indexed)"},
                    "endLine": {"type": "integer", "description": "The ending line number of the chunk (1-indexed)"}
                },
                "required": ["path", "targetContent", "replacementContent", "startLine", "endLine"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ls",
            "description": "List directory contents",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path to the directory"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find",
            "description": "Recursively searches for files by name/glob.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in"},
                    "pattern": {"type": "string", "description": "File name pattern or glob to match (e.g. *.ts)"}
                },
                "required": ["path", "pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Recursively searches for text within files using regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search in"},
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "include": {"type": "string", "description": "Glob pattern to filter files (e.g. *.py)"}
                },
                "required": ["path", "pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Execute a bash command non-interactively. IMPORTANT: Commands execute without TTY input. Always pass non-interactive flags (e.g. 'npx -y ...', 'npm create vite@latest app -- --template react --yes', 'npm init -y', 'pip install --no-input'). Do not run commands that wait for user prompt input.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute in the terminal"}
                },
                "required": ["command"]
            }
        }
    }
]

async def execute_tool(name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON arguments provided: {e}")
        
    if not isinstance(args, dict):
        raise ValueError("JSON arguments must be a dictionary/object.")

    if name == "read":
        return await handle_read(args)
    elif name == "write":
        return await handle_write(args)
    elif name == "edit":
        return await handle_edit(args)
    elif name == "ls":
        return await handle_ls(args)
    elif name == "find":
        return await handle_find(args)
    elif name == "grep":
        return await handle_grep(args)
    elif name == "bash" or name == "bash_command":
        command = args.get("command")
        if not command:
            raise ValueError("Missing 'command' argument.")
        return await execute_bash(command)
        
    raise ValueError(f"Unknown tool {name}")
