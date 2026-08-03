from fastapi import APIRouter
from typing import List
from app.schemas.search import ScrapeRequest, ScrapedDocument
from app.services.scraper import ScraperService

router = APIRouter()


@router.post("", response_model=List[ScrapedDocument])
async def scrape_urls(request: ScrapeRequest):
    """
    Parallel async DOM parsing & HTML sanitization endpoint.
    """
    urls_str = [str(u) for u in request.urls]
    results = await ScraperService.scrape_parallel(urls_str)
    return [
        ScrapedDocument(
            url=res["url"],
            content=res["content"],
            error=res.get("error")
        )
        for res in results
    ]
