import os

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
