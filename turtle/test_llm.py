import asyncio
import sys
from turtle.llm import LLMClient

async def test():
    client = LLMClient(provider="antigravity", model="gemini-3.5-flash-low")
    print(f"Base URL: {client.base_url}")
    print(f"API Key: {client.api_key}")
    
    models = await client.get_models()
    print(f"Models: {models}")
    
    messages = [{"role": "user", "content": "Hello!"}]
    try:
        async for chunk in client.stream_chat(messages):
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    print(delta.content, end="")
                    sys.stdout.flush()
        print("\n[Stream completed]")
    except Exception as e:
        print(f"\n[Error during stream: {e}]")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test())
