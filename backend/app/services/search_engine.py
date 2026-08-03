import httpx
from typing import List
from app.schemas.chat import Citation, ModeType
from app.core.config import settings
from app.core.logging import logger


class SearchEngineService:
    @staticmethod
    async def query(query: str, mode: ModeType = "auto", max_results: int = 5) -> List[Citation]:
        """
        Aggregates search results from Tavily, Bing, or fallback mock search.
        """
        if settings.TAVILY_API_KEY:
            try:
                return await SearchEngineService._query_tavily(query, max_results)
            except Exception as e:
                logger.error(f"Tavily search failed: {e}")

        if settings.BING_API_KEY:
            try:
                return await SearchEngineService._query_bing(query, max_results)
            except Exception as e:
                logger.error(f"Bing search failed: {e}")

        # Fallback search provider simulation/mock for initial dev
        return SearchEngineService._mock_search(query, max_results)

    @staticmethod
    async def _query_tavily(query: str, max_results: int) -> List[Citation]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results
                }
            )
            data = res.json()
            citations = []
            for idx, item in enumerate(data.get("results", []), 1):
                citations.append(Citation(
                    id=idx,
                    title=item.get("title", "Untitled"),
                    url=item.get("url", "https://example.com"),
                    snippet=item.get("content", "")[:300]
                ))
            return citations

    @staticmethod
    async def _query_bing(query: str, max_results: int) -> List[Citation]:
        headers = {"Ocp-Apim-Subscription-Key": settings.BING_API_KEY}
        params = {"q": query, "count": max_results}
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params)
            data = res.json()
            citations = []
            for idx, item in enumerate(data.get("webPages", {}).get("value", []), 1):
                citations.append(Citation(
                    id=idx,
                    title=item.get("name", "Untitled"),
                    url=item.get("url", "https://example.com"),
                    snippet=item.get("snippet", "")[:300]
                ))
            return citations

    @staticmethod
    def _mock_search(query: str, max_results: int) -> List[Citation]:
        return [
            Citation(
                id=1,
                title=f"Sample Search Result for '{query}'",
                url="https://en.wikipedia.org/wiki/Main_Page",
                snippet=f"This is an automated fallback search result snippet providing background context for: {query}."
            ),
            Citation(
                id=2,
                title="Documentation & Reference Guide",
                url="https://docs.python.org/3/",
                snippet=f"Detailed reference data and technical documentation relevant to {query}."
            )
        ][:max_results]
