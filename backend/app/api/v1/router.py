from fastapi import APIRouter
from app.api.v1.endpoints import chat, search, scrape, intent, research, transcribe

api_router = APIRouter()

api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(scrape.router, prefix="/scrape", tags=["scrape"])
api_router.include_router(intent.router, prefix="/intent", tags=["intent"])
api_router.include_router(research.router, prefix="/research", tags=["research"])
api_router.include_router(transcribe.router, prefix="/transcribe", tags=["transcribe"])
