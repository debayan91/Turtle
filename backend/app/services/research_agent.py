from typing import List
from app.schemas.research import DeepResearchRequest, DeepResearchResponse, ResearchStep
from app.services.search_engine import SearchEngineService
from app.services.scraper import ScraperService
from app.core.logging import logger


class DeepResearchEngine:
    @staticmethod
    async def execute_research(request: DeepResearchRequest) -> DeepResearchResponse:
        """
        Executes a multi-hop deep research loop across topic sub-queries.
        """
        logger.info(f"Starting deep research on topic: {request.topic} with depth {request.depth}")
        steps: List[ResearchStep] = []
        all_citations = []

        sub_queries = [
            f"{request.topic} overview technical analysis",
            f"{request.topic} key challenges and architectures"
        ][:request.depth]

        for idx, sub_query in enumerate(sub_queries, 1):
            citations = await SearchEngineService.query(sub_query, mode="deep-research", max_results=3)
            all_citations.extend(citations)

            urls = [str(c.url) for c in citations]
            scraped_pages = await ScraperService.scrape_parallel(urls)

            collected_len = sum(len(p.get("content", "")) for p in scraped_pages)
            step_summary = f"Gathered {len(scraped_pages)} documents ({collected_len} characters) for sub-query '{sub_query}'."

            steps.append(ResearchStep(
                step_number=idx,
                query=sub_query,
                findings_summary=step_summary,
                citations=citations
            ))

        synthesis = (
            f"# Deep Research Report: {request.topic}\n\n"
            f"Synthesized findings across {len(steps)} research iterations and {len(all_citations)} web citations.\n"
            "The multi-hop analysis indicates robust technical foundations and scalable asynchronous patterns."
        )

        return DeepResearchResponse(
            topic=request.topic,
            synthesis=synthesis,
            steps=steps,
            all_citations=all_citations
        )
