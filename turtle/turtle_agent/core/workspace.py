import asyncio
import json
import logging
import os
import sqlite3
import uuid
import time
from datetime import datetime

log = logging.getLogger(__name__)

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    cwd TEXT NOT NULL,
    parent_session_id TEXT NULL,
    metadata TEXT NULL
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_cwd_created_at ON sessions(cwd, created_at DESC);

CREATE TABLE IF NOT EXISTS entries (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    id TEXT NOT NULL,
    parent_id TEXT NULL,
    type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (session_id, id),
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_entries_session_parent ON entries(session_id, parent_id);
CREATE INDEX IF NOT EXISTS idx_entries_session_type_seq ON entries(session_id, type, seq);

CREATE TABLE IF NOT EXISTS session_sequences (
    session_id TEXT PRIMARY KEY,
    next_seq INTEGER NOT NULL
) WITHOUT ROWID;
"""

class WorkspaceState:
    """
    Manages session isolation per workspace directory using SQLite.
    Translates exact `pi` schema for sessions, entries, and sequences.
    """
    def __init__(self, workspace_dir: str = None):
        if not workspace_dir:
            workspace_dir = os.getcwd()
        self.workspace_dir = os.path.abspath(workspace_dir)
        
        self.db_dir = os.path.expanduser("~/.trtl")
        os.makedirs(self.db_dir, exist_ok=True)
        self.db_path = os.path.join(self.db_dir, "sessions.db")
        
        self._lock = asyncio.Lock()
        self.session_id: str = None
        self.current_node_id: str | None = None
        self.load_warnings: list[str] = []
        
        self._init_db()
        self._load_session()

    def _get_connection(self):
        # Enable WAL mode for concurrency, just like pi
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript(DB_SCHEMA)

    def _load_session(self):
        with self._get_connection() as conn:
            # Check if an existing session for this cwd exists
            cursor = conn.execute(
                "SELECT id FROM sessions WHERE cwd = ? ORDER BY created_at DESC LIMIT 1",
                (self.workspace_dir,)
            )
            row = cursor.fetchone()
            
            if row:
                self.session_id = row["id"]
                # Find the leaf node (highest seq)
                cursor = conn.execute(
                    "SELECT id FROM entries WHERE session_id = ? ORDER BY seq DESC LIMIT 1",
                    (self.session_id,)
                )
                leaf_row = cursor.fetchone()
                if leaf_row:
                    self.current_node_id = leaf_row["id"]
            else:
                self.session_id = str(uuid.uuid4())
                now_str = datetime.utcnow().isoformat() + "Z"
                conn.execute(
                    "INSERT INTO sessions (id, created_at, cwd) VALUES (?, ?, ?)",
                    (self.session_id, now_str, self.workspace_dir)
                )
                conn.execute(
                    "INSERT INTO session_sequences (session_id, next_seq) VALUES (?, ?)",
                    (self.session_id, 1)
                )
                self.current_node_id = None

    def _get_next_seq(self, conn) -> int:
        cursor = conn.execute(
            "SELECT next_seq FROM session_sequences WHERE session_id = ?",
            (self.session_id,)
        )
        row = cursor.fetchone()
        seq = row["next_seq"] if row else 1
        
        conn.execute(
            "UPDATE session_sequences SET next_seq = next_seq + 1 WHERE session_id = ?",
            (self.session_id,)
        )
        return seq

    def has_valid_system_root(self) -> bool:
        if not self.current_node_id:
            return False
            
        with self._get_connection() as conn:
            # We walk back up the tree looking for role="system"
            current = self.current_node_id
            visited = set()
            while current:
                if current in visited:
                    return False
                visited.add(current)
                
                cursor = conn.execute(
                    "SELECT parent_id, type, payload FROM entries WHERE session_id = ? AND id = ?",
                    (self.session_id, current)
                )
                row = cursor.fetchone()
                if not row:
                    return False
                    
                payload = json.loads(row["payload"])
                parent_id = row["parent_id"]
                
                if not parent_id:
                    return payload.get("role") == "system"
                current = parent_id
                
        return False

    def get_messages(self, head_id: str | None = None) -> list:
        current = head_id or self.current_node_id
        messages = []
        seen = set()
        
        with self._get_connection() as conn:
            while current:
                if current in seen:
                    log.error("Cycle in state graph at node %s; stopping traversal", current)
                    break
                seen.add(current)
                
                cursor = conn.execute(
                    "SELECT parent_id, payload FROM entries WHERE session_id = ? AND id = ?",
                    (self.session_id, current)
                )
                row = cursor.fetchone()
                if not row:
                    break
                    
                payload = json.loads(row["payload"])
                
                clean_msg = {k: v for k, v in payload.items() if k not in ("id", "parent_id")}
                messages.append(clean_msg)
                
                current = row["parent_id"]
                
        return messages[::-1]

    async def append_message(
        self,
        role: str,
        content: str | None = None,
        tool_calls: list | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> str:
        msg_id = str(uuid.uuid4())
        
        payload: dict = {"id": msg_id, "parent_id": self.current_node_id, "role": role}
        if content is not None:
            payload["content"] = content
        if tool_calls is not None:
            payload["tool_calls"] = tool_calls
        if tool_call_id is not None:
            payload["tool_call_id"] = tool_call_id
        if name is not None:
            payload["name"] = name
            
        def _write():
            with self._get_connection() as conn:
                seq = self._get_next_seq(conn)
                now_str = datetime.utcnow().isoformat() + "Z"
                
                conn.execute(
                    """INSERT INTO entries (session_id, seq, id, parent_id, type, timestamp, payload) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.session_id,
                        seq,
                        msg_id,
                        self.current_node_id,
                        "message",  # Matches pi's entry type mapping
                        now_str,
                        json.dumps(payload)
                    )
                )

        async with self._lock:
            await asyncio.to_thread(_write)

        self.current_node_id = msg_id
        return msg_id

    async def reset(self) -> None:
        async with self._lock:
            def _delete():
                with self._get_connection() as conn:
                    # In Pi, we wouldn't drop the table, we just create a new session or delete rows
                    conn.execute("DELETE FROM entries WHERE session_id = ?", (self.session_id,))
                    conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
                    conn.execute("DELETE FROM session_sequences WHERE session_id = ?", (self.session_id,))
            await asyncio.to_thread(_delete)
            
        # Reinitialize session after reset
        self.session_id = None
        self._load_session()
