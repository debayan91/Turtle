import asyncio
import sys
from turtle_agent import Agent

async def run_mcp_server():
    agent = Agent()
    print("MCP Server interface mock running...")
    await agent.close()

if __name__ == "__main__":
    asyncio.run(run_mcp_server())
