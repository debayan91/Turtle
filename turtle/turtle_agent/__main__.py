import asyncio
import sys

import uvloop

from turtle_agent.agent import run_agent

def main():
    # Install uvloop as the default event loop policy
    uvloop.install()
    
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\nExiting turtle agent.")
        sys.exit(0)

if __name__ == "__main__":
    main()
