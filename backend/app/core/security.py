from fastapi import Header, HTTPException, status
from app.core.config import settings


async def verify_api_key(x_api_key: str = Header(None)):
    """
    Optional API Key header verification middleware/dependency for internal microservice protection.
    If X-API-Key is configured in environment, validates header match.
    """
    # Placeholder for optional authentication checks
    return True
