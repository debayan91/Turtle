from fastapi import APIRouter
from openai import AsyncOpenAI
from app.schemas.intent import IntentRequest, IntentClassificationResponse
from app.services.intent_classifier import IntentService
from app.core.config import settings

router = APIRouter()
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "dummy-key")
intent_service = IntentService(client=openai_client)


@router.post("", response_model=IntentClassificationResponse)
async def classify_intent(request: IntentRequest):
    """
    Prompt intent classifier endpoint for auto-routing queries to optimal search modes and domains.
    """
    res = await intent_service.classify(request.query)
    return IntentClassificationResponse(
        mode=res.get("mode", "auto"),
        search_queries=res.get("search_queries", [request.query]),
        target_domains=res.get("target_domains", []),
        requires_search=res.get("requires_search", True),
        confidence=res.get("confidence", 1.0)
    )
