import json
from typing import AsyncGenerator, List
from openai import AsyncOpenAI
from app.schemas.chat import ChatRequest, Citation
from app.core.config import settings
from app.core.logging import logger


class LLMStreamingService:
    def __init__(self, client: AsyncOpenAI = None):
        self.client = client or AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "dummy-key")

    async def generate_stream(
        self, request: ChatRequest, citations: List[Citation], context_text: str
    ) -> AsyncGenerator[str, None]:
        """
        Yields Server-Sent Events (SSE) compatible string chunks.
        """
        # Yield citations first as metadata event
        if citations:
            citation_payload = [c.model_dump(mode="json") for c in citations]
            yield f"data: {json.dumps({'type': 'citation', 'data': json.dumps(citation_payload)})}\n\n"

        # System prompt with retrieved context grounding
        system_content = (
            "You are an intelligent search assistant. Answer the query concisely and accurately using "
            "the provided context documents. Cite sources using [1], [2], etc., matching the provided citation IDs.\n\n"
            f"Context Documents:\n{context_text}"
        )

        messages = [{"role": "system", "content": system_content}]
        messages.extend([{"role": m.role, "content": m.content} for m in request.messages])

        if not settings.OPENAI_API_KEY:
            # Demonstration mock streaming if OpenAI API Key is missing
            mock_tokens = [
                "Based on the retrieved context, ",
                "here is the summarized answer for your search request. ",
                "The core architecture utilizes asynchronous FastAPI, ",
                "multi-provider search, and SSE streaming for low-latency delivery [1]."
            ]
            for token in mock_tokens:
                yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            stream = await self.client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                top_p=request.top_p,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    token = chunk.choices[0].delta.content
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'data': token})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Error in LLM streaming: {e}")
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
