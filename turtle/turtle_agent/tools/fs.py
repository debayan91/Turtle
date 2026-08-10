import os
import itertools
import shlex
from .utils import truncate_output, _resolve_path
from .bash import execute_bash

async def handle_read(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    
    try:
        offset_val = args.get("offset")
        limit_val = args.get("limit")
        
        try:
            offset = int(offset_val) if offset_val is not None else None
            limit = int(limit_val) if limit_val is not None else None
        except (ValueError, TypeError):
            raise ValueError("'offset' and 'limit' must be valid integers.")
            
        start_idx = max(0, offset - 1) if offset else 0
        
        with open(path, "r", encoding="utf-8") as f:
            if limit:
                selected_lines = list(itertools.islice(f, start_idx, start_idx + limit))
            else:
                selected_lines = list(itertools.islice(f, start_idx, None))
                
        output = "".join(selected_lines)
        return truncate_output(output)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found at path '{path}'")
    except PermissionError:
        raise PermissionError(f"Permission denied reading '{path}'")
    except UnicodeDecodeError:
        raise ValueError(f"File at '{path}' is not valid UTF-8 text")
    except Exception as e:
        raise Exception(f"Error reading file: {str(e)}")

async def handle_write(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    content = args.get("content", "")
    
    try:
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except PermissionError:
        raise PermissionError(f"Permission denied writing to '{path}'. Check directory permissions.")
    except Exception as e:
        raise Exception(f"Error writing file: {str(e)}")

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
        raise FileNotFoundError(f"Directory not found: '{path}'")
    except NotADirectoryError:
        raise NotADirectoryError(f"Path is not a directory: '{path}'")
    except PermissionError:
        raise PermissionError(f"Permission denied listing directory '{path}'")
    except Exception as e:
        raise Exception(f"Error listing directory: {str(e)}")

async def handle_find(args: dict) -> str:
    path = _resolve_path(args.get("path", "."))
    pattern = args.get("pattern", "")
    
    if not pattern:
        raise ValueError("pattern is required")
        
    cmd = f"find {shlex.quote(path)} -name {shlex.quote(pattern)}"
    return await execute_bash(cmd)

async def handle_grep(args: dict) -> str:
    path = _resolve_path(args.get("path", "."))
    pattern = args.get("pattern", "")
    include = args.get("include", "")
    
    if not pattern:
        raise ValueError("pattern is required")
        
    cmd = f"grep -rn {shlex.quote(path)} -e {shlex.quote(pattern)}"
    if include:
        cmd += f" --include={shlex.quote(include)}"
        
    return await execute_bash(cmd)
