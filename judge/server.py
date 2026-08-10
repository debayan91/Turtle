import json
import time
import asyncio
import uuid
import os
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

def get_judge_state():
    state_file = "/tmp/judge_state.json"
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return json.load(f)
    return {"scenario": "firehose", "mode": "zero_latency"}

def load_scenario(name: str):
    path = os.path.join(os.path.dirname(__file__), "scenarios", f"{name}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)

def create_chat_chunk(content, chunk_id=None):
    if not chunk_id:
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    return {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "gpt-4-mock",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}]
    }

def create_tool_call_chunk(name, arguments, chunk_id=None, is_first=False):
    if not chunk_id:
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    delta = {}
    if is_first:
        delta["tool_calls"] = [{"index": 0, "id": f"call_{uuid.uuid4().hex}", "type": "function", "function": {"name": name, "arguments": arguments}}]
    else:
         delta["tool_calls"] = [{"index": 0, "function": {"arguments": arguments}}]
    return {
        "id": chunk_id, "object": "chat.completion.chunk", "created": int(time.time()),
        "model": "gpt-4-mock", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]
    }

def create_finish_chunk(chunk_id=None, finish_reason="stop"):
    if not chunk_id:
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
    return {
        "id": chunk_id, "object": "chat.completion.chunk", "created": int(time.time()),
        "model": "gpt-4-mock", "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]
    }

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    state = get_judge_state()
    mode = state.get("mode", "zero_latency")
    scenario_name = state.get("scenario", "firehose")
    
    scenario = load_scenario(scenario_name)
    if not scenario:
        return {"error": f"Scenario {scenario_name} not found"}

    messages = body.get("messages", [])
    
    async def generate_sse():
        delay = 0.01 if mode == "simulated_network" else 0
        chunk_id = f"chatcmpl-{uuid.uuid4().hex}"
        
        # Log TTFR start time
        with open("/tmp/judge_ttfr_start.txt", "w") as f:
            f.write(str(time.perf_counter()))

        if scenario["type"] == "firehose":
            total_tokens = scenario.get("total_tokens", 50000)
            chunk_size = scenario.get("chunk_size", 20)
            text = scenario.get("text", "word ")
            
            tokens_sent = 0
            while tokens_sent < total_tokens:
                if delay > 0:
                    await asyncio.sleep(delay)
                chunk_text = text * chunk_size
                chunk = create_chat_chunk(chunk_text, chunk_id)
                yield f"data: {json.dumps(chunk)}\n\n"
                tokens_sent += chunk_size
                
            if delay > 0:
                await asyncio.sleep(delay)
            yield f"data: {json.dumps(create_finish_chunk(chunk_id))}\n\n"
            
        elif scenario["type"] == "ping_pong":
            tool_calls_in_history = sum(1 for m in messages if m.get("role") == "tool" or m.get("role") == "function")
            target_count = scenario.get("count", 100)
            
            if delay > 0:
                await asyncio.sleep(delay)
                
            if tool_calls_in_history >= target_count:
                yield f"data: {json.dumps(create_chat_chunk('Test complete', chunk_id))}\n\n"
                yield f"data: {json.dumps(create_finish_chunk(chunk_id, 'stop'))}\n\n"
            else:
                tool_name = scenario.get("tool_name", "run_command")
                tool_args = json.dumps(scenario.get("tool_args", {"command": "echo 'hello'"}))
                yield f"data: {json.dumps(create_tool_call_chunk(tool_name, '', chunk_id, True))}\n\n"
                yield f"data: {json.dumps(create_tool_call_chunk('', tool_args, chunk_id, False))}\n\n"
                yield f"data: {json.dumps(create_finish_chunk(chunk_id, 'tool_calls'))}\n\n"
                
        elif scenario["type"] == "fat_context":
            if delay > 0:
                await asyncio.sleep(delay)
            yield f"data: {json.dumps(create_chat_chunk(f'Received {len(messages)} messages in context.', chunk_id))}\n\n"
            yield f"data: {json.dumps(create_finish_chunk(chunk_id))}\n\n"
            
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate_sse(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
