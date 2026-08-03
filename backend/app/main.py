from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.exceptions import global_exception_handler
from app.core.logging import logger
from app.api.v1.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="FastAPI backend core for low-latency RAG, web search aggregation, intent classification, and multi-step agentic research."
)

# Exception handler registration
app.add_exception_handler(Exception, global_exception_handler)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Route registration
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["system"])
def health_check():
    """Health check endpoint for service probes."""
    return {"status": "operational", "project": settings.PROJECT_NAME}


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.PROJECT_NAME} backend service...")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {settings.PROJECT_NAME} backend service...")
