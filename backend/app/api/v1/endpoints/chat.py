from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI

from app.schemas.chat import ChatRequest
from app.services.llm import LLMStreamingService
from app.services.search_engine import SearchEngineService
from app.services.scraper import ScraperService
from app.services.intent_classifier import IntentService
from app.core.config import settings

router = APIRouter()
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "dummy-key")
llm_service = LLMStreamingService(client=openai_client)
intent_service = IntentService(client=openai_client)


@router.post("/stream")
async def stream_chat(request: ChatRequest):
    """
    RAG chat endpoint yielding Server-Sent Events (SSE).
    1. Classifies user query intent
    2. Performs multi-provider web search
    3. Scrapes top web pages in parallel
    4. Streams grounded LLM responses with citations
    """
    last_user_msg = request.messages[-1].content if request.messages else ""

    # Step 1: Intent Classification
    intent = await intent_service.classify(last_user_msg)
    mode = intent.get("mode", request.mode)

    # Step 2: Web Search Aggregation
    citations = await SearchEngineService.query(
        query=last_user_msg,
        mode=mode,
        max_results=4
    )

    # Step 3: Parallel Web Scraping
    urls = [str(c.url) for c in citations]
    scraped_docs = await ScraperService.scrape_parallel(urls)

    # Format retrieved context
    context_blocks = []
    for doc, citation in zip(scraped_docs, citations):
        content = doc.get("content", "")
        if content:
            context_blocks.append(f"Source [{citation.id}] - {citation.title} ({citation.url}):\n{content}")

    context_text = "\n\n".join(context_blocks) if context_blocks else "No external documents retrieved."

    # Step 4: Stream response
    return StreamingResponse(
        llm_service.generate_stream(request, citations, context_text),
        media_type="text/event-stream"
    )
