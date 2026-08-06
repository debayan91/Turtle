import sys
import asyncio
from turtle.agent import Agent

async def run_turtle_headless(prompt: str):
    agent = Agent()
    # Process prompt using turtle's uvloop + httpx engine
    response = await agent.run_single_turn(prompt)
    print(response)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        asyncio.run(run_turtle_headless(prompt))
