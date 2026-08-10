from mcp.server.fastmcp import FastMCP
import asyncio
from turtle_agent.agent import Agent

mcp = FastMCP("Turtle-Fast-Agent")

# H-6: Do NOT instantiate Agent at module level.
# Agent.__init__ reads state.jsonl (blocking I/O) and opens an httpx client.
# Both are unsafe before the event loop is running, and they prevent
# concurrent MCP calls from getting independent sessions.
_agent: Agent | None = None
_agent_lock = asyncio.Lock()

async def _get_agent() -> Agent:
    global _agent
    async with _agent_lock:
        if _agent is None:
            _agent = Agent()
    return _agent

@mcp.tool()
async def run_fast_turtle_agent(task: str) -> str:
    """Executes a coding task using the ultra-fast Python turtle engine."""
    agent = await _get_agent()
    return await agent.run_single_turn(task)

if __name__ == "__main__":
    mcp.run(transport="stdio")
