import asyncio
import os
import sys

from turtle_agent.agent import AgentState
from turtle_agent.llm import LLMClient
from turtle_agent.tools import execute_tool, TOOLS_SCHEMA

async def test_tool_call_parsing():
    # Simulate tool call stream chunks
    from prompt_toolkit import Application
    # We won't use TUI, just mock it
    pass

if __name__ == "__main__":
    pass
