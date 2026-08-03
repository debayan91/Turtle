from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from app.schemas.chat import Citation, ModeType


class SearchRequest(BaseModel):
    query: str
    mode: ModeType = "auto"
    max_results: int = 5
    domains: Optional[List[str]] = None


class SearchResponse(BaseModel):
    query: str
    citations: List[Citation]


class ScrapeRequest(BaseModel):
    urls: List[HttpUrl]
    max_chars_per_page: Optional[int] = 5000


class ScrapedDocument(BaseModel):
    url: str
    content: str
    error: Optional[str] = None
