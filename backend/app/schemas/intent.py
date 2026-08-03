from pydantic import BaseModel
from typing import List, Optional
from app.schemas.chat import ModeType


class IntentRequest(BaseModel):
    query: str


class IntentClassificationResponse(BaseModel):
    mode: ModeType
    search_queries: List[str]
    target_domains: List[str] = []
    requires_search: bool = True
    confidence: float = 1.0
