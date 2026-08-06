from mcp.server.fastmcp import FastMCP
import asyncio
from turtle.agent import Agent

mcp = FastMCP("Turtle-Fast-Agent")
turtle_agent = Agent()

@mcp.tool()
async def run_fast_turtle_agent(task: str) -> str:
    """Executes a coding task using the ultra-fast Python turtle engine."""
    # Leverages turtle's uvloop + msgspec stack
    return await turtle_agent.run_single_turn(task)

if __name__ == "__main__":
    mcp.run(transport="stdio")
