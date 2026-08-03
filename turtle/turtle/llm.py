import os
import httpx
import msgspec
from typing import AsyncGenerator, Dict, Any, List, Optional

# Define zero-overhead msgspec structures for fast JSON parsing
class FunctionCall(msgspec.Struct):
    name: Optional[str] = None
    arguments: Optional[str] = None

class ToolCall(msgspec.Struct):
    index: int
    id: Optional[str] = None
    type: Optional[str] = None
    function: Optional[FunctionCall] = None

class Delta(msgspec.Struct, omit_defaults=True):
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None

class Choice(msgspec.Struct):
    delta: Delta

class ChatCompletionChunk(msgspec.Struct):
    choices: List[Choice]

class LLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is missing.")
        
        self.base_url = base_url
        
        # Keep connection open and persistent, use HTTP/2
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            http2=True,
            timeout=httpx.Timeout(120.0)
        )
        self.decoder = msgspec.json.Decoder(ChatCompletionChunk)

    async def stream_chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[ChatCompletionChunk, None]:
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        # Stream the SSE response
        async with self.client.stream("POST", "/chat/completions", content=msgspec.json.encode(payload)) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = self.decoder.decode(data_str.encode("utf-8"))
                        yield chunk
                    except msgspec.DecodeError:
                        pass # Ignore malformed chunks

    async def close(self):
        await self.client.aclose()
