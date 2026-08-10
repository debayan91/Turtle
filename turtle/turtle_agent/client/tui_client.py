import asyncio
import json
import logging
import os
import sys
import subprocess
import urllib.parse
import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from ..tui.app import TurtleTUI

DAEMON_WS_BASE = "ws://127.0.0.1:8000"
DAEMON_HTTP_BASE = "http://127.0.0.1:8000"

FOOTER_DISCONNECTED = " NORMAL | <style fg='#7aa2f7'>main</style> | <style fg='#f7768e'>Disconnected</style> | <style fg='#565f89'>Alt+Enter: newline, Ctrl+C: exit</style>"
FOOTER_CONNECTED    = " NORMAL | <style fg='#7aa2f7'>main</style> | <style fg='#9ece6a'>Connected</style> | <style fg='#565f89'>Alt+Enter: newline, Ctrl+C: exit</style>"


# ── Daemon lifecycle ───────────────────────────────────────────────────────────

async def _daemon_alive() -> bool:
    """Return True if the daemon HTTP health endpoint responds."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as c:
            r = await c.get(f"{DAEMON_HTTP_BASE}/health")
            return r.status_code == 200
    except Exception:
        return False


async def ensure_daemon_running(tui: TurtleTUI) -> str:
    """
    Make sure the daemon is running, starting it in the background if needed.
    Returns the ws:// URL to connect to, or raises RuntimeError.
    """
    ws_url = (
        DAEMON_WS_BASE
        + "/ws/chat?workspace_dir="
        + urllib.parse.quote(os.getcwd())
    )

    if await _daemon_alive():
        return ws_url

    tui.append_transcript("[#565f89]⠋ Starting daemon in background...[/]")

    subprocess.Popen(
        [sys.executable, "-m", "turtle_agent.server.daemon"],
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    for _ in range(20):           # wait up to 10 s
        await asyncio.sleep(0.5)
        if await _daemon_alive():
            tui.append_transcript(
                "[#a9b1d6]▸[/] [#7aa2f7]Daemon[/]\n"
                "  [#565f89]└─[/] [#9ece6a]✓ started and connected[/]"
            )
            return ws_url

    raise RuntimeError(
        "Daemon did not start in time. "
        "Check logs or run `python -m turtle_agent.server.daemon` manually."
    )


# ── Model helpers ──────────────────────────────────────────────────────────────

async def fetch_models() -> list[str]:
    """Fetch the model list from the daemon's REST endpoint."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{DAEMON_HTTP_BASE}/models")
            r.raise_for_status()
            return r.json().get("models", [])
    except Exception:
        return []


# ── Command dispatcher (client-side — never reaches the LLM) ──────────────────

async def handle_slash_command(
    cmd: str,
    tui: TurtleTUI,
    websocket,
    current_model: list,       # mutable 1-element list so we can update it
) -> bool:
    """
    Handle all /commands locally.
    Returns True if the command was consumed (don't send to LLM).
    """
    cmd = cmd.strip()
    parts = cmd.split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb == "/help":
        tui.append_transcript(
            "\n[#a9b1d6]▸[/] [#7aa2f7]Available Commands[/]\n"
            "  [#565f89]├─[/] [#9ece6a]/help[/]          - Show this menu\n"
            "  [#565f89]├─[/] [#9ece6a]/model[/]         - Interactive model selector (arrow keys)\n"
            "  [#565f89]├─[/] [#9ece6a]/models[/]        - Interactive model selector (arrow keys)\n"
            "  [#565f89]├─[/] [#9ece6a]/clear[/]         - Clear session context\n"
            "  [#565f89]└─[/] [#9ece6a]/exit[/]          - Exit Turtle\n"
        )
        return True

    if verb in ("/models", "/model"):
        selected_model = None
        if arg:
            selected_model = arg
        else:
            models = await fetch_models()
            if not models:
                tui.append_transcript(
                    "\n[#f7768e]✗[/] [#a9b1d6]Could not retrieve models from daemon.[/]\n"
                )
                return True
            selected_model = await tui.prompt_model_picker(models, current_model[0])

        if selected_model:
            try:
                async with httpx.AsyncClient(timeout=5.0) as c:
                    r = await c.post(
                        f"{DAEMON_HTTP_BASE}/model",
                        json={"model": selected_model},
                    )
                    r.raise_for_status()
                current_model[0] = selected_model
                tui.append_transcript(
                    f"\n[#a9b1d6]▸[/] [#7aa2f7]Configuration[/]\n"
                    f"  [#565f89]└─[/] [#9ece6a]✓ Model switched to {selected_model}[/]\n"
                )
            except Exception as e:
                tui.append_transcript(
                    f"\n[#f7768e]✗[/] [#a9b1d6]Failed to switch model: {e}[/]\n"
                )
        return True

    if verb == "/clear":
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                qs = urllib.parse.quote(os.getcwd())
                r = await c.post(f"{DAEMON_HTTP_BASE}/clear?workspace_dir={qs}")
                r.raise_for_status()
        except Exception:
            pass
        tui.append_transcript(
            "\n[#a9b1d6]▸[/] [#7aa2f7]Session[/]\n"
            "  [#565f89]└─[/] [#9ece6a]✓ Context cleared[/]\n"
        )
        return True

    # Unknown slash command
    tui.append_transcript(
        f"\n[#f7768e]✗[/] [#a9b1d6]Unknown command: {cmd}[/] — type [#9ece6a]/help[/] for a list.\n"
    )
    return True


# ── Main client ────────────────────────────────────────────────────────────────

async def run_agent_client():
    input_queue: asyncio.Queue[str] = asyncio.Queue()
    interrupt_event = asyncio.Event()
    current_model = ["gemini-3.5-flash-low"]   # mutable reference

    tui = TurtleTUI(
        input_queue=input_queue,
        exit_callback=lambda: None,
        interrupt_callback=interrupt_event.set,
    )

    tui.layout_engine.update_footer(FOOTER_DISCONNECTED)

    async def process_loop():
        try:
            tui.append_transcript("[#565f89]⠋ Connecting to Turtle Daemon...[/]")
            ws_url = await ensure_daemon_running(tui)

            async with connect(ws_url) as websocket:
                tui.layout_engine.update_footer(FOOTER_CONNECTED)
                tui.app.invalidate()

                while True:
                    user_input = await input_queue.get()
                    stripped = user_input.strip()

                    # ── Exit commands ──────────────────────────────────────
                    if stripped in ("/exit", "/quit"):
                        try:
                            if not tui.app.is_done:
                                tui.app.exit()
                        except Exception:
                            pass
                        break

                    # ── All slash commands intercepted here ────────────────
                    if stripped.startswith("/"):
                        await handle_slash_command(
                            stripped, tui, websocket, current_model
                        )
                        continue

                    # ── Normal message → daemon ────────────────────────────
                    tui.append_transcript(
                        f"\n[#a9b1d6]▸[/] [#7aa2f7]You[/]\n"
                        f"  [#565f89]└─[/] {user_input}"
                    )
                    await websocket.send(json.dumps({"prompt": user_input}))
                    tui.append_transcript("[#565f89]⠋ Thinking...[/]")

                    while True:
                        try:
                            msg = await websocket.recv()
                            data = json.loads(msg)

                            if data.get("type") == "chunk":
                                tui.append_transcript(data["content"], is_markdown=True)
                            elif data.get("type") == "tool_event":
                                name = data.get("name", "?")
                                status = data.get("status", "done")
                                icon = "✓" if status == "ok" else "✗"
                                color = "#9ece6a" if status == "ok" else "#f7768e"
                                tui.append_transcript(
                                    f"\n[#a9b1d6]▸[/] [#7aa2f7]Tool[/]\n"
                                    f"  [#565f89]└─[/] [{color}]{icon} {name}[/]\n"
                                )
                            elif data.get("type") == "done":
                                break
                            elif data.get("type") == "error":
                                tui.display_error(data.get("message", "Unknown error"))
                                break
                        except ConnectionClosed:
                            tui.display_error("Connection to daemon lost.")
                            tui.layout_engine.update_footer(FOOTER_DISCONNECTED)
                            tui.app.invalidate()
                            return
                        except Exception as e:
                            tui.display_error(f"Stream error: {e}")
                            break

        except Exception as e:
            tui.display_error(str(e))

    try:
        tui_task = asyncio.create_task(tui.run_async())
        proc_task = asyncio.create_task(process_loop())

        done, pending = await asyncio.wait(
            [tui_task, proc_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    except asyncio.CancelledError:
        pass
