import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict
from app.core.config import settings
from app.core.logging import logger


class ScraperService:
    @staticmethod
    async def fetch_and_clean(url: str) -> Dict[str, str]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        try:
            async with httpx.AsyncClient(timeout=settings.SCRAPE_TIMEOUT_SECONDS) as client:
                resp = await client.get(url, headers=headers, follow_redirects=True)
                if resp.status_code != 200:
                    return {"url": url, "content": "", "error": f"HTTP status {resp.status_code}"}

                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                    tag.decompose()

                text = soup.get_text(separator=" ", strip=True)
                cleaned_text = text[:settings.MAX_SCRAPE_CHARS_PER_PAGE]
                return {"url": url, "content": cleaned_text, "error": None}
        except Exception as e:
            logger.warning(f"Error scraping {url}: {str(e)}")
            return {"url": url, "content": "", "error": str(e)}

    @classmethod
    async def scrape_parallel(cls, urls: List[str]) -> List[Dict[str, str]]:
        return await asyncio.gather(*(cls.fetch_and_clean(url) for url in urls))
