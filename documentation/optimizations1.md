# Turtle Latency Optimization — Walkthrough

## Summary

Applied 4 layers of latency optimization to bring Turtle's TTFT closer to native Antigravity speed.

**TTFB Results (curl → `localhost:3000`):**
| | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|
| **Before** | 1.52s | 1.84s | 1.85s | — | — |
| **After** | 1.37s | 1.63s | 0.99s | 0.71s | 0.60s |

Warm-state improvement: **~1.7s → ~0.7s (2.4× faster)**

---

## Changes Made

### 1. Proxy Endpoint Routing — `config.json` (×3 files)

**Files:** [config.json](file:///Users/debayan/Documents/projects/turtle/config.json), [turtle/config.json](file:///Users/debayan/Documents/projects/turtle/turtle/config.json), `~/proxy_dummy/config.json`

- Stripped `daily-cloudcode-pa`, `sandbox`, and `autopush` endpoints. Now routes exclusively through production `cloudcode-pa.googleapis.com`.
- Disabled artificial jitter (`jitterEnabled: false`, `jitterMinMs/Max: 0`), removing the 50–300ms random delay per request.
- Restarted the proxy process to pick up the new config.

### 2. Stream Buffering Elimination — [`llm.py`](file:///Users/debayan/Documents/projects/turtle/turtle/turtle_agent/core/llm.py)

- Replaced `response.aiter_lines()` with `response.aiter_bytes()` + manual SSE line splitting. This yields chunks the instant bytes arrive on the socket rather than waiting for httpx's internal line buffer to fill.
- Added `Accept: text/event-stream` and `X-Accel-Buffering: no` headers to signal the proxy to disable all buffering.
- Fixed a `StreamClosed` bug in the `HTTPStatusError` handler that would crash when trying to read the response body from an already-closed stream context.

### 3. Connection Reuse — [`tui_client.py`](file:///Users/debayan/Documents/projects/turtle/turtle/turtle_agent/client/tui_client.py)

- Added a module-level persistent `httpx.AsyncClient` (`_get_daemon_client()`) with keep-alive.
- Replaced all 4 sites that created `async with httpx.AsyncClient() as c:` per call (`_daemon_alive`, `fetch_models`, `/model` switch, `/clear`) with the shared client.
- Eliminates TCP handshake + HTTP negotiation overhead on every daemon interaction.

### 4. Workspace Query Optimization — [`workspace.py`](file:///Users/debayan/Documents/projects/turtle/turtle/turtle_agent/core/workspace.py)

- Cached a persistent SQLite connection (`self._conn`) instead of opening/closing one per operation.
- Added a fast-path `get_messages()` using a single `ORDER BY seq ASC` query for linear conversations (the common case), avoiding N parent-chasing queries.
- Preserved the traversal method as `_get_messages_by_traversal()` for branched history lookups (used by `/checkout`).

---

## What Was Tested

- **Curl TTFB benchmark:** 3 baseline runs, then 5 post-optimization runs against `localhost:3000`
- **Python imports:** `LLMClient`, `WorkspaceState`, `tui_client` all import cleanly
- **LLMClient E2E:** Verified new headers are set, `get_models()` returns 19 models, stream parser works
- **WorkspaceState E2E:** Verified fast-path returns correct message order, connection caching returns same instance
- **Proxy restart:** Confirmed proxy re-launched from `~/proxy_dummy/` with updated config, serving on port 3000

---

## Remaining Optimization Opportunities

- **Proxy-side connection pooling** to Google PA endpoints — requires inspecting/modifying the `antigravity-proxy` TypeScript source itself
- **Proactive OAuth token refresh** — currently the proxy may refresh tokens reactively during the request path
- **Context compression** — implementing a `/compact` command that summarizes long histories before sending to the LLM
