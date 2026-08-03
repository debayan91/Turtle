from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal

ModeType = Literal[
    "auto",
    "deep-research",
    "academic",
    "reddit",
    "youtube",
    "chat",
    "stock",
    "weather",
    "dictionary"
]


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Citation(BaseModel):
    id: int
    title: str
    url: HttpUrl
    snippet: str


class ChatRequest(BaseModel):
    messages: List[Message]
    mode: ModeType = "auto"
    model: str = "gpt-4o"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: Optional[int] = 4000
    stream: bool = True


class SSEChunk(BaseModel):
    """Standardized format for Server-Sent Events."""
    type: Literal["token", "citation", "status", "thought", "error", "done"]
    data: str


class StreamChunk(BaseModel):
    event: Literal["token", "citation", "thought", "error", "done"]
    data: str
