"""
AutoHeal DevOps — Configuration & Environment Management
"""

from functools import lru_cache
from typing import List, Literal, Optional, Union
import json
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    Follows 12-factor principles with safe development defaults and robust aliases.
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
    APP_ENV: Literal["development", "staging", "production", "test"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
        description="Application runtime environment"
    )
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    SECRET_KEY: str = Field(
        default="autoheal_insecure_dev_secret_change_in_production_1234567890",
        validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET_KEY"),
        description="Master encryption and cryptographic signature key"
    )

    # API Prefix
    API_V1_STR: str = "/api/v1"

    # CORS Allowed Origins
    CORS_ORIGINS: Union[List[str], str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://autoheal-omega.vercel.app",
            "https://autoheal-devops.vercel.app",
        ],
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS"),
        description="List or comma-separated string of trusted CORS origins"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        default_origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "https://autoheal-omega.vercel.app",
            "https://autoheal-devops.vercel.app",
        ]
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        value = parsed
                except Exception:
                    pass
        if isinstance(value, str):
            origins = [i.strip() for i in value.split(",") if i.strip()]
            for o in default_origins:
                if o not in origins:
                    origins.append(o)
            return origins
        elif isinstance(value, list):
            res = list(value)
            for o in default_origins:
                if o not in res:
                    res.append(o)
            return res
        return default_origins

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db",
        description="Async PostgreSQL connection URI"
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, value: str) -> str:
        if not value:
            return value
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://") and not value.startswith("postgresql+"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Normalize cloud PostgreSQL SSL query parameter for asyncpg dialect
        if "sslmode=" in value:
            value = (
                value.replace("sslmode=require", "ssl=require")
                .replace("sslmode=prefer", "ssl=prefer")
                .replace("sslmode=disable", "ssl=disable")
                .replace("sslmode=verify-full", "ssl=verify-full")
                .replace("sslmode=verify-ca", "ssl=verify-ca")
            )
        return value

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Redis Broker & Cache
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "CELERY_BROKER_URL"),
        description="Redis connection URI for Celery tasks and session revocation"
    )
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # Cookie & Authentication Settings
    COOKIE_SECURE: Optional[bool] = None
    COOKIE_SAMESITE: Optional[str] = None
    COOKIE_DOMAIN: Optional[str] = None

    # JWT & Authentication
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SSE_TICKET_EXPIRE_SECONDS: int = 60
    AGENT_SECRET_KEY: str = "autoheal_agent_secret_key_32chars_long"

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

    # Recovery Automation Engine
    MAX_RECOVERY_RETRIES: int = 3
    RECOVERY_COOLDOWN_SECONDS: int = 300


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached Settings singleton instance.
    """
    return Settings()
