from pydantic import BaseModel
from typing import List, Optional
from app.schemas.chat import Citation


class DeepResearchRequest(BaseModel):
    topic: str
    depth: int = 2
    max_sources: int = 10


class ResearchStep(BaseModel):
    step_number: int
    query: str
    findings_summary: str
    citations: List[Citation]


class DeepResearchResponse(BaseModel):
    topic: str
    synthesis: str
    steps: List[ResearchStep]
    all_citations: List[Citation]
