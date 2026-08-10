"""
Turtle Agent Daemon
-------------------
FastAPI server that drives the agent loop.  Exposes:
  WS  /ws/chat?workspace_dir=<path>  — streaming conversation
  GET /health                         — liveness probe
  GET /models                         — list available models
  POST /model  { model: str }         — switch active model
  POST /clear?workspace_dir=<path>    — wipe session context
"""
import asyncio
import json
import logging
import os
from typing import Dict

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from ..core.workspace import WorkspaceState
from ..core.agent_loop import run_agent_turn
from ..core.llm import LLMClient

log = logging.getLogger(__name__)

app = FastAPI(title="Turtle Agent Daemon", version="1.0.0")

# ── Shared state ───────────────────────────────────────────────────────────────

# One WorkspaceState per CWD
_workspaces: Dict[str, WorkspaceState] = {}
# One LLMClient shared across all connections (model is mutable)
_llm_client: LLMClient | None = None


def _get_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def _get_workspace(workspace_dir: str) -> WorkspaceState:
    if workspace_dir not in _workspaces:
        _workspaces[workspace_dir] = WorkspaceState(workspace_dir)
    return _workspaces[workspace_dir]


# ── REST endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/models")
async def list_models():
    try:
        client = _get_client()
        models = await client.get_models()
        # Fallback hardcoded list if provider returns nothing
        if not models:
            models = [
                "gemini-3.5-flash-low",
                "gemini-3.5-flash",
                "gemini-3.5-pro",
                "gemini-3.1-pro-high",
                "claude-3.5-sonnet",
                "claude-3-opus",
                "gpt-4o",
                "gpt-4-turbo",
            ]
        return {"models": models}
    except Exception as e:
        log.warning("Could not fetch models: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/model")
async def set_model(payload: dict):
    model = payload.get("model", "").strip()
    if not model:
        return JSONResponse(status_code=400, content={"error": "model field required"})
    client = _get_client()
    client.model = model
    log.info("Model switched to %s", model)
    return {"model": model}


@app.post("/clear")
async def clear_session(workspace_dir: str):
    ws = _get_workspace(workspace_dir)
    await ws.reset()
    log.info("Cleared session for %s", workspace_dir)
    return {"cleared": True}


# ── WebSocket chat ─────────────────────────────────────────────────────────────

@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, workspace_dir: str):
    await websocket.accept()

    workspace = _get_workspace(workspace_dir)
    client = _get_client()

    async def send(payload: dict):
        await websocket.send_text(json.dumps(payload))

    async def yield_text(text: str):
        """Stream raw LLM text chunks to the client."""
        await send({"type": "chunk", "content": text})

    async def yield_tool_event(name: str, status: str):
        """Notify client about a tool execution result."""
        await send({"type": "tool_event", "name": name, "status": status})

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            prompt = payload.get("prompt", "").strip()
            if not prompt:
                continue

            # Ensure system message exists
            if not workspace.has_valid_system_root():
                await workspace.append_message(
                    "system",
                    "You are Turtle, an ultra-fast local CLI coding agent. "
                    "Be concise, direct, and accurate. "
                    "When the user asks to write or edit code, do it — don't describe what you're going to do."
                )

            try:
                await run_agent_turn(
                    workspace, client, prompt,
                    yield_text_callback=yield_text,
                    yield_tool_callback=yield_tool_event,
                )
                await send({"type": "done"})
            except Exception as e:
                log.exception("Error in agent turn")
                await send({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        log.info("Client disconnected: %s", workspace_dir)
    except Exception as e:
        log.error("WebSocket error: %s", e)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="warning",  # suppress access logs in the background
    )
