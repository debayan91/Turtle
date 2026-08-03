import json
from typing import Dict, Any
from openai import AsyncOpenAI
from app.schemas.chat import ModeType
from app.core.config import settings
from app.core.logging import logger


class IntentService:
    def __init__(self, client: AsyncOpenAI = None):
        self.client = client or AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "dummy-key")

    async def classify(self, prompt: str) -> Dict[str, Any]:
        """
        Classifies prompt intent into ModeType, search queries, and target domain filters.
        """
        if not settings.OPENAI_API_KEY:
            # Rule-based fallback classifier if API key is not configured yet
            return self._fallback_classify(prompt)

        try:
            system_prompt = (
                "You are an intent classification engine for an AI search system. "
                "Analyze the user query and return JSON with keys: "
                "'mode' (one of 'auto', 'deep-research', 'academic', 'reddit', 'youtube', 'chat', 'stock', 'weather'), "
                "'search_queries' (list of refined strings for web search), "
                "'target_domains' (list of domain filters e.g. ['arxiv.org'] or empty), "
                "'requires_search' (boolean)."
            )
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Intent classification LLM call failed: {e}. Using fallback classification.")
            return self._fallback_classify(prompt)

    def _fallback_classify(self, prompt: str) -> Dict[str, Any]:
        p_lower = prompt.lower()
        mode: ModeType = "auto"
        domains = []

        if "arxiv" in p_lower or "paper" in p_lower or "academic" in p_lower:
            mode = "academic"
            domains = ["arxiv.org", "scholar.google.com"]
        elif "reddit" in p_lower:
            mode = "reddit"
            domains = ["reddit.com"]
        elif "youtube" in p_lower or "video" in p_lower:
            mode = "youtube"
            domains = ["youtube.com"]
        elif "stock" in p_lower or "price" in p_lower or "market" in p_lower:
            mode = "stock"

        return {
            "mode": mode,
            "search_queries": [prompt],
            "target_domains": domains,
            "requires_search": True,
            "confidence": 0.95
        }
