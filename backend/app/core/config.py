from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Search Engine Core"
    API_V1_STR: str = "/api/v1"

    # Provider Keys
    OPENAI_API_KEY: str = ""
    BING_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # Execution Constraints
    MAX_SCRAPE_CHARS_PER_PAGE: int = 5000
    SCRAPE_TIMEOUT_SECONDS: float = 8.0
    MAX_TOKENS_DEFAULT: int = 4000

    # Security & CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
