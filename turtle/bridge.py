import asyncio
import sys
from turtle_agent import Agent

async def run_bridge():
    agent = Agent()
    print("Bridge interface mock running...")
    await agent.close()

if __name__ == "__main__":
    asyncio.run(run_bridge())
