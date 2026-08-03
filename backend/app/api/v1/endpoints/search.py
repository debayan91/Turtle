from fastapi import APIRouter
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_engine import SearchEngineService

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def search_web(request: SearchRequest):
    """
    Direct web search proxy endpoint with domain filtering and multi-provider aggregation.
    """
    citations = await SearchEngineService.query(
        query=request.query,
        mode=request.mode,
        max_results=request.max_results
    )
    return SearchResponse(query=request.query, citations=citations)
