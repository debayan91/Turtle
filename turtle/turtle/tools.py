import asyncio
from typing import Dict, Any, List
import json

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "bash_command",
            "description": "Execute a bash command.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute in the terminal"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

async def execute_tool(name: str, arguments: str) -> str:
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        return "Error: Invalid JSON arguments provided."

    if name == "bash_command":
        command = args.get("command")
        if not command:
            return "Error: Missing command argument."
        
        # Execute asynchronously without blocking the main thread
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        stdout, _ = await process.communicate()
        return stdout.decode("utf-8", errors="replace")
    
    return f"Error: Unknown tool {name}"
