import asyncio
import json
import logging
import os
import urllib.parse
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ..tui.app import TurtleTUI

async def run_agent_client():
    input_queue = asyncio.Queue()
    interrupt_event = asyncio.Event()

    def _exit_cb():
        pass
        
    def _interrupt_cb():
        interrupt_event.set()

    tui = TurtleTUI(input_queue=input_queue, exit_callback=_exit_cb, interrupt_callback=_interrupt_cb)
    
    workspace_dir = urllib.parse.quote(os.getcwd())
    ws_url = f"ws://127.0.0.1:8000/ws/chat?workspace_dir={workspace_dir}"

    tui.layout_engine.update_footer(f"<b>Turtle</b> | Connected to Daemon | Use <style bg='ansiyellow' fg='ansiblack'>Alt+Enter</style> for newline, <style bg='ansiyellow' fg='ansiblack'>Ctrl+C</style> to exit")
    tui.append_transcript("[bold green]Connecting to Turtle Daemon...[/bold green]")

    async def process_loop():
        try:
            async with connect(ws_url) as websocket:
                tui.append_transcript("[bold green]Connected successfully.[/bold green]")
                
                while True:
                    user_input = await input_queue.get()
                    if user_input.startswith("/exit") or user_input.startswith("/quit"):
                        tui.app.exit()
                        break
                        
                    tui.append_transcript(f"\n[bold blue]You:[/bold blue] {user_input}")
                    await websocket.send(json.dumps({"prompt": user_input}))
                    
                    tui.append_transcript("[bold blue]Turtle is thinking...[/bold blue]")
                    
                    while True:
                        try:
                            msg = await websocket.recv()
                            data = json.loads(msg)
                            
                            if data.get("type") == "chunk":
                                tui.append_transcript(data["content"], is_markdown=True)
                            elif data.get("type") == "done":
                                break
                            elif data.get("type") == "error":
                                tui.display_error(data["message"])
                                break
                        except ConnectionClosed:
                            tui.display_error("Connection to daemon lost.")
                            break
                        except Exception as e:
                            tui.display_error(f"Error reading from daemon: {e}")
                            break
                            
        except Exception as e:
            tui.display_error(f"Failed to connect to daemon at {ws_url}: {e}")
            tui.append_transcript("Please ensure you have started the daemon with `python -m turtle_agent.server.daemon`")

    try:
        tui_task = asyncio.create_task(tui.run_async())
        process_task = asyncio.create_task(process_loop())
        
        done, pending = await asyncio.wait(
            [tui_task, process_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
    except asyncio.CancelledError:
        pass
