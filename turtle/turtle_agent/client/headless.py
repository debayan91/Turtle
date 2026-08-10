import asyncio
from ..core.workspace import WorkspaceState
from ..core.llm import LLMClient
from ..core.agent_loop import run_agent_turn

class Agent:
    """
    Headless Agent API for Antigravity JSON Hooks and MCP.
    Maintains backward compatibility with scripts expecting a local agent loop.
    """
    def __init__(self, workspace_dir: str = None) -> None:
        self.state = WorkspaceState(workspace_dir)
        try:
            self.client = LLMClient()
        except ValueError:
            self.client = LLMClient(provider="antigravity", model="gemini-3.5-pro")
            
        self._system_initialized = self.state.has_valid_system_root()

    async def _initialize_system_prompt(self) -> None:
        sys_prompt = "You are Turtle, an ultra-fast local CLI coding agent."
        if getattr(self, "load_warnings", []):
            sys_prompt += "\n\n--- System Warnings ---\n" + "\n".join(self.load_warnings)
        await self.state.append_message("system", sys_prompt)
        self._system_initialized = True

    async def close(self) -> None:
        if self.client:
            await self.client.close()

    async def run_single_turn(self, prompt: str) -> str:
        if not self._system_initialized:
            await self._initialize_system_prompt()

        return await run_agent_turn(self.state, self.client, prompt)
