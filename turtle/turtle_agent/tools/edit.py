import os
from .utils import _resolve_path

# TODO: Enhance with line-range patching or unified diff parsing
# For now, keeping the string replace but with better error reporting.

async def handle_edit(args: dict) -> str:
    path = _resolve_path(args.get("path", ""))
    target = args.get("targetContent", "")
    replacement = args.get("replacementContent", "")
    
    try:
        # Check size to prevent OOM
        file_size = os.path.getsize(path)
        if file_size > 100000 * 10:  # e.g., 1MB limit for edits
            raise ValueError(f"File at '{path}' is too large to edit directly ({file_size} bytes). Use sed or awk via bash.")
            
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if target not in content:
            raise ValueError("targetContent not found in file. Ensure exact match including whitespace.")
            
        if content.count(target) > 1:
            raise ValueError("targetContent found multiple times in file. Please provide a larger unique context chunk.")
            
        new_content = content.replace(target, replacement)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        return f"Successfully edited {path}"
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found at path '{path}'")
    except PermissionError:
        raise PermissionError(f"Permission denied editing '{path}'")
    except ValueError as e:
        raise e
    except Exception as e:
        raise Exception(f"Error editing file: {str(e)}")
