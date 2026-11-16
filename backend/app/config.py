"""
AutoHeal DevOps — Configuration & Environment Management
"""

from functools import lru_cache
from typing import List, Literal, Optional, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    Follows 12-factor principles with safe development defaults.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    APP_NAME: str = "AutoHeal DevOps API"
    APP_VERSION: str = "0.1.0"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    SECRET_KEY: str = Field(
        default="autoheal_insecure_dev_secret_change_in_production_1234567890",
        description="Master encryption and cryptographic signature key"
    )

    # API Prefix
    API_V1_STR: str = "/api/v1"

    # CORS Allowed Origins
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://autoheal-devops.vercel.app"
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str) and not value.startswith("["):
            return [i.strip() for i in value.split(",") if i.strip()]
        elif isinstance(value, list):
            return value
        return ["http://localhost:3000"]

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db",
        description="Async PostgreSQL connection URI"
    )

    # Redis Broker & Cache
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URI for Celery tasks and session revocation"
    )

    # JWT & Authentication
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Default Multi-Tenant Organization
    DEFAULT_ORGANIZATION_NAME: str = "AutoHeal Workspace"
    DEFAULT_ORGANIZATION_SLUG: str = "autoheal-workspace"

    # AI Diagnosis Provider
    AI_PROVIDER: Literal["gemini", "anthropic", "openai", "none"] = "none"
    AI_API_KEY: Optional[str] = None
    AI_MODEL: str = "gemini-1.5-pro"
    AI_TIMEOUT_SECONDS: float = 8.0

    # Monitoring & Alerting
    PROMETHEUS_URL: str = "http://localhost:9090"
    ALERTMANAGER_HMAC_SECRET: str = "autoheal_alertmanager_webhook_hmac_secret_key_12345"
    METRIC_SCRAPE_INTERVAL_SECONDS: int = 15


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached Settings singleton instance.
    """
    return Settings()
