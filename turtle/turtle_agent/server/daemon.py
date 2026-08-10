import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import uvicorn

from ..core.workspace import WorkspaceState
from ..core.agent_loop import run_agent_turn
from ..core.llm import LLMClient

log = logging.getLogger(__name__)

app = FastAPI(title="Turtle Agent Daemon")

# In-memory session store (workspace_dir -> WorkspaceState)
active_workspaces = {}

def get_workspace(workspace_dir: str) -> WorkspaceState:
    if workspace_dir not in active_workspaces:
        active_workspaces[workspace_dir] = WorkspaceState(workspace_dir)
    return active_workspaces[workspace_dir]

@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket, workspace_dir: str):
    await websocket.accept()
    
    workspace = get_workspace(workspace_dir)
    try:
        client = LLMClient()
    except ValueError:
        client = LLMClient(provider="antigravity", model="gemini-3.5-pro")
        
    try:
        while True:
            data = await websocket.receive_text()
            message_payload = json.loads(data)
            prompt = message_payload.get("prompt")
            
            if not prompt:
                continue

            async def yield_to_client(text: str):
                await websocket.send_text(json.dumps({"type": "chunk", "content": text}))
                
            try:
                # System prompt init (simplistic for now)
                if not workspace.has_valid_system_root():
                    await workspace.append_message("system", "You are Turtle, an ultra-fast local CLI coding agent.")
                
                await run_agent_turn(workspace, client, prompt, yield_to_client)
                await websocket.send_text(json.dumps({"type": "done"}))
            except Exception as e:
                log.error(f"Error running agent turn: {e}")
                await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
                
    except WebSocketDisconnect:
        log.info(f"Client disconnected from workspace {workspace_dir}")
    except Exception as e:
        log.error(f"WebSocket error: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
