import asyncio
import sys

import uvloop

from .client.tui_client import run_agent_client

def main():
    uvloop.install()
    
    try:
        asyncio.run(run_agent_client())
    except KeyboardInterrupt:
        print("\nExiting turtle agent.")
        sys.exit(0)

if __name__ == "__main__":
    main()
