from fastapi import APIRouter
from app.schemas.research import DeepResearchRequest, DeepResearchResponse
from app.services.research_agent import DeepResearchEngine

router = APIRouter()


@router.post("", response_model=DeepResearchResponse)
async def deep_research(request: DeepResearchRequest):
    """
    Deep Research agent multi-hop iterative DAG loop endpoint.
    """
    return await DeepResearchEngine.execute_research(request)
