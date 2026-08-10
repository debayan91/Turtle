import os
import asyncio
from .utils import truncate_output

# TODO: Add PTY support and real-time streaming back to daemon.

async def execute_bash(command: str, timeout: float = 300.0) -> str:
    process = None
    env = os.environ.copy()
    env.update({
        "CI": "true",
        "DEBIAN_FRONTEND": "noninteractive",
        "PIP_NO_INPUT": "1",
        "NPM_CONFIG_YES": "true",
    })
    
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        return truncate_output(stdout.decode("utf-8", errors="replace"))
    except asyncio.TimeoutError:
        if process is not None:
            try:
                os.killpg(os.getpgid(process.pid), 9)
            except OSError:
                pass
        raise TimeoutError(
            f"Command timed out after {int(timeout)} seconds. "
            "If the command was waiting for interactive input (e.g. prompt confirmations), "
            "make sure to pass non-interactive flags (e.g. 'npx -y ...', 'npm create ... -- --yes')."
        )
    except asyncio.CancelledError:
        if process is not None:
            try:
                os.killpg(os.getpgid(process.pid), 9)
            except OSError:
                pass
        raise
    except Exception as e:
        raise Exception(f"Error executing bash: {str(e)}")
