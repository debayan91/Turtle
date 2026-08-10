import asyncio
import json
import os
import re
import shlex
import itertools
from typing import Dict, Any, List

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
            "description": "Execute a bash command.",
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

MAX_OUTPUT_CHARS = 100000  # ~100kb
MAX_LINES = 1000

def truncate_output(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n... [Truncated: exceeded {MAX_OUTPUT_CHARS} chars] ..."
    
    lines = text.split("\n")
    if len(lines) > MAX_LINES:
        text = "\n".join(lines[:MAX_LINES]) + f"\n... [Truncated: exceeded {MAX_LINES} lines] ..."
        
    return text

def _resolve_path(path_str: str) -> str:
    return os.path.abspath(os.path.expanduser(path_str))

async def handle_read(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    
    try:
        offset_val = args.get("offset")
        limit_val = args.get("limit")
        
        try:
            offset = int(offset_val) if offset_val is not None else None
            limit = int(limit_val) if limit_val is not None else None
        except (ValueError, TypeError):
            return "Error: 'offset' and 'limit' must be valid integers."
            
        start_idx = max(0, offset - 1) if offset else 0
        
        with open(path, "r", encoding="utf-8") as f:
            if limit:
                selected_lines = list(itertools.islice(f, start_idx, start_idx + limit))
            else:
                selected_lines = list(itertools.islice(f, start_idx, None))
                
        output = "".join(selected_lines)
        return truncate_output(output)
    except FileNotFoundError:
        return f"Error: File not found at path '{path}'"
    except PermissionError:
        return f"Error: Permission denied reading '{path}'"
    except UnicodeDecodeError:
        return f"Error: File at '{path}' is not valid UTF-8 text"
    except Exception as e:
        return f"Error reading file: {str(e)}"

async def handle_write(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    content = args.get("content", "")
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except PermissionError:
        return f"Error: Permission denied writing to '{path}'. Check directory permissions."
    except Exception as e:
        return f"Error writing file: {str(e)}"

async def handle_edit(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    target = args.get("targetContent", "")
    replacement = args.get("replacementContent", "")
    
    try:
        # Check size to prevent OOM
        file_size = os.path.getsize(path)
        if file_size > MAX_OUTPUT_CHARS * 10:  # e.g., 1MB limit for edits
            return f"Error: File at '{path}' is too large to edit directly ({file_size} bytes). Use sed or awk via bash."
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if target not in content:
            return "Error: targetContent not found in file. Ensure exact match including whitespace."
            
        if content.count(target) > 1:
            return "Error: targetContent found multiple times in file. Please provide a larger unique context chunk."
            
        new_content = content.replace(target, replacement)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Successfully edited {path}"
    except FileNotFoundError:
        return f"Error: File not found at path '{path}'"
    except PermissionError:
        return f"Error: Permission denied editing '{path}'"
    except Exception as e:
        return f"Error editing file: {str(e)}"

async def handle_ls(args: dict) -> str:
    path = _resolve_path(args.get("path", "."))
    
    try:
        entries = os.listdir(path)
        output = []
        for e in sorted(entries):
            full_p = os.path.join(path, e)
            if os.path.isdir(full_p):
                output.append(f"{e}/")
            else:
                size = os.path.getsize(full_p)
                output.append(f"{e} ({size} bytes)")
        return truncate_output("\n".join(output))
    except FileNotFoundError:
        return f"Error: Directory not found: '{path}'"
    except NotADirectoryError:
        return f"Error: Path is not a directory: '{path}'"
    except PermissionError:
        return f"Error: Permission denied listing directory '{path}'"
    except Exception as e:
        return f"Error listing directory: {str(e)}"

async def handle_find(args: dict) -> str:
    path = _resolve_path(args.get("path", "."))
    pattern = args.get("pattern", "")
    
    if not pattern:
        return "Error: pattern is required"
        
    cmd = f"find {shlex.quote(path)} -name {shlex.quote(pattern)}"
    return await execute_bash(cmd)

async def handle_grep(args: dict) -> str:
    path = _resolve_path(args.get("path", "."))
    pattern = args.get("pattern", "")
    include = args.get("include", "")
    
    if not pattern:
        return "Error: pattern is required"
        
    cmd = f"grep -rnw {shlex.quote(path)} -e {shlex.quote(pattern)}"
    if include:
        cmd += f" --include={shlex.quote(include)}"
        
    return await execute_bash(cmd)

async def execute_bash(command: str) -> str:
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            preexec_fn=os.setsid
        )
        # Timeout to prevent hanging tasks forever
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=120.0)
        return truncate_output(stdout.decode("utf-8", errors="replace"))
    except asyncio.TimeoutError:
        try:
            os.killpg(os.getpgid(process.pid), 9)
        except OSError:
            pass
        return f"Error: Command timed out after 120 seconds."
    except asyncio.CancelledError:
        try:
            os.killpg(os.getpgid(process.pid), 9)
        except OSError:
            pass
        raise
    except Exception as e:
        return f"Error executing bash: {str(e)}"

async def execute_tool(name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        return "Error: Invalid JSON arguments provided."
        
    if not isinstance(args, dict):
        return "Error: JSON arguments must be a dictionary/object."

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
            return "Error: Missing command argument."
        return await execute_bash(command)
        
    return f"Error: Unknown tool {name}"
