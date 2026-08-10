import os
import json
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

PROVIDERS = {
    "openai": {"env": "OPENAI_API_KEY", "url": "https://api.openai.com/v1"},
    "deepseek": {"env": "DEEPSEEK_API_KEY", "url": "https://api.deepseek.com/v1"},
    "openrouter": {"env": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1"},
    "groq": {"env": "GROQ_API_KEY", "url": "https://api.groq.com/openai/v1"},
    "together": {"env": "TOGETHER_API_KEY", "url": "https://api.together.xyz/v1"},
    "anthropic": {"env": "ANTHROPIC_API_KEY", "url": "https://api.anthropic.com/v1"}, # Note: Anthropic uses a different API schema natively, but included for translation completeness.
    "antigravity": {"env": "ANTIGRAVITY_API_KEY", "url": "http://localhost:3000/v1"}
}

class LLMClient:
    def __init__(self, provider: str = "antigravity", model: str = "gemini-3.5-flash-low", api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = provider
        self.model = model
        
        provider_config = PROVIDERS.get(self.provider, {})
        
        # 1. Resolve API Key
        self.api_key = api_key
        if not self.api_key:
            # Try auth.json
            auth_file = os.path.expanduser("~/.pi/agent/auth.json")
            if os.path.exists(auth_file):
                try:
                    with open(auth_file, "r") as f:
                        auth_data = json.load(f)
                        if self.provider in auth_data:
                            self.api_key = auth_data[self.provider].get("key")
                except json.JSONDecodeError:
                    print(f"Warning: Failed to parse {auth_file}. The file might be corrupted.")
                except OSError as e:
                    print(f"Warning: Could not read {auth_file}: {e}")
            
            # Try Environment Variable
            env_key = f"{self.provider.upper()}_API_KEY"
            if not self.api_key and "env" in provider_config:
                self.api_key = os.getenv(provider_config["env"])
            elif not self.api_key:
                self.api_key = os.getenv(env_key)
                
        # 2. Resolve Base URL
        env_base_url = f"{self.provider.upper()}_BASE_URL"
        self.base_url = base_url or os.getenv(env_base_url) or os.getenv("OPENAI_BASE_URL") or provider_config.get("url", "https://api.openai.com/v1")
                
        if not self.api_key:
            if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
                self.api_key = "local-dummy-key"
            else:
                raise ValueError(f"API key for provider '{self.provider}' is missing. Please set it in ~/.pi/agent/auth.json or via {provider_config.get('env', env_key)}.")
        
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

    async def get_models(self) -> List[str]:
        """Fetch available models from the provider's /models endpoint."""
        try:
            response = await self.client.get("/models")
            response.raise_for_status()
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    async def stream_chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> AsyncGenerator[ChatCompletionChunk, None]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        # Stream the SSE response
        try:
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
        except httpx.TimeoutException as e:
            raise RuntimeError(f"LLM API request timed out: {e}")
        except httpx.HTTPStatusError as e:
            error_body = await e.response.aread() if not e.response.is_stream_consumed else b"<stream consumed>"
            raise RuntimeError(f"LLM API returned HTTP {e.response.status_code}: {error_body.decode(errors='replace')}")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network error while connecting to LLM API: {e}")

    async def close(self):
        await self.client.aclose()
