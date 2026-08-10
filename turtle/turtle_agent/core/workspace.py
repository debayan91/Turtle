import asyncio
import json
import logging
import os
import tempfile
import uuid
import hashlib

log = logging.getLogger(__name__)

class WorkspaceState:
    """
    Manages session isolation per workspace directory.
    Stores state in ~/.trtl/workspaces/<hash>.jsonl
    """
    def __init__(self, workspace_dir: str = None):
        if not workspace_dir:
            workspace_dir = os.getcwd()
        self.workspace_dir = os.path.abspath(workspace_dir)
        
        # Isolate session states by taking a hash of the workspace path
        path_hash = hashlib.md5(self.workspace_dir.encode('utf-8')).hexdigest()
        self._state_dir = os.path.expanduser("~/.trtl/workspaces")
        os.makedirs(self._state_dir, exist_ok=True)
        self.state_file = os.path.join(self._state_dir, f"{path_hash}.jsonl")
        
        self.nodes: dict = {}
        self.current_node_id: str | None = None
        self.load_warnings: list[str] = []
        self._lock = asyncio.Lock()
        self._load_state()

    def _load_state(self) -> None:
        if not os.path.exists(self.state_file):
            return
        corrupt = False
        with open(self.state_file, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                    if "id" not in msg:
                        raise ValueError("Missing 'id' field")
                    self.nodes[msg["id"]] = msg
                    self.current_node_id = msg["id"]
                except (json.JSONDecodeError, ValueError) as exc:
                    self.load_warnings.append(
                        f"Warning: Corrupt line {line_idx + 1} in {self.state_file}: {exc}"
                    )
                    corrupt = True
                except Exception as exc:
                    self.load_warnings.append(f"Error loading state: {exc}")
        if corrupt:
            self.load_warnings.append(
                f"Warning: {self.state_file} has corrupt lines; they are ignored."
            )

    def has_valid_system_root(self) -> bool:
        if not self.nodes:
            return False
        visited: set[str] = set()
        current = self.current_node_id
        while current:
            if current in visited:
                return False  # cycle detected
            visited.add(current)
            node = self.nodes.get(current)
            if node is None:
                return False
            parent = node.get("parent_id")
            if not parent:
                return node.get("role") == "system"
            current = parent
        return False

    def get_messages(self, head_id: str | None = None) -> list:
        current = head_id or self.current_node_id
        messages = []
        seen: set[str] = set()
        while current:
            if current in seen:
                log.error("Cycle in state graph at node %s; stopping traversal", current)
                break
            seen.add(current)
            msg = self.nodes.get(current)
            if not msg:
                break
            clean_msg = {k: v for k, v in msg.items() if k not in ("id", "parent_id")}
            messages.append(clean_msg)
            current = msg.get("parent_id")
        return messages[::-1]

    def get_lineage(self, head_id: str | None = None) -> list:
        current = head_id or self.current_node_id
        nodes = []
        seen: set[str] = set()
        while current:
            if current in seen:
                log.error("Cycle in state graph at node %s; stopping traversal", current)
                break
            seen.add(current)
            msg = self.nodes.get(current)
            if not msg:
                break
            nodes.append(msg)
            current = msg.get("parent_id")
        return nodes[::-1]

    async def append_message(
        self,
        role: str,
        content: str | None = None,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> str:
        msg_id = uuid.uuid4().hex[:8]
        msg: dict = {"id": msg_id, "parent_id": self.current_node_id, "role": role}
        if content is not None:
            msg["content"] = content
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_call_id is not None:
            msg["tool_call_id"] = tool_call_id
        if name is not None:
            msg["name"] = name

        def _write() -> None:
            state_dir = os.path.dirname(self.state_file)
            try:
                fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
                try:
                    existing = ""
                    if os.path.exists(self.state_file):
                        with open(self.state_file, "r", encoding="utf-8") as src:
                            existing = src.read()
                    with os.fdopen(fd, "w", encoding="utf-8") as dst:
                        dst.write(existing)
                        dst.write(json.dumps(msg) + "\n")
                    os.replace(tmp_path, self.state_file)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise
            except OSError as exc:
                log.error("Failed to persist message to %s: %s", self.state_file, exc)
                raise

        async with self._lock:
            await asyncio.to_thread(_write)

        self.nodes[msg_id] = msg
        self.current_node_id = msg_id
        return msg_id

    async def reset(self) -> None:
        async with self._lock:
            def _delete():
                if os.path.exists(self.state_file):
                    os.remove(self.state_file)
            await asyncio.to_thread(_delete)
        self.nodes = {}
        self.current_node_id = None
        self.load_warnings = []
