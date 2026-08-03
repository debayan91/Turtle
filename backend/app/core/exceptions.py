from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse


class ServiceUnavailableException(HTTPException):
    def __init__(self, detail: str = "External service unavailable"):
        super().__init__(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)


class LLMException(HTTPException):
    def __init__(self, detail: str = "Error generating response from LLM provider"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


class SearchException(HTTPException):
    def __init__(self, detail: str = "Search provider error"):
        super().__init__(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred.", "error": str(exc)},
    )
