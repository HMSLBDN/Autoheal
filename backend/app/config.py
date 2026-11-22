"""
AutoHeal DevOps — Configuration & Environment Management
"""

import json
import urllib.parse
from functools import lru_cache
from typing import List, Literal, Optional, Union
from pydantic import AliasChoices, Field, field_validator, model_validator
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

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(
        default=True,
        description="Enable sliding-window rate limiting on sensitive authentication endpoints"
    )

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
        # Preserve SQLite URLs untouched (e.g. sqlite+aiosqlite:///:memory:)
        if value.startswith("sqlite"):
            return value
        try:
            from sqlalchemy.engine import make_url
            url = make_url(value)
            driver = url.drivername
            if driver in ("postgres", "postgresql"):
                driver = "postgresql+asyncpg"
            query = dict(url.query)
            if "sslmode" in query:
                sslmode_val = query.pop("sslmode")
                valid_modes = {"disable", "prefer", "require", "verify-ca", "verify-full"}
                if sslmode_val not in valid_modes:
                    raise ValueError(
                        f"Invalid PostgreSQL sslmode: '{sslmode_val}'. Supported modes are: {sorted(valid_modes)}"
                    )
                query["ssl"] = sslmode_val
            return url.set(drivername=driver, query=query).render_as_string(hide_password=False)
        except ValueError:
            raise
        except Exception:
            return value

    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    # Database SSL / TLS Settings
    DB_SSL_MODE: Optional[Literal["disable", "prefer", "require", "verify-ca", "verify-full"]] = None
    DB_SSL_CA_CERT: Optional[str] = None
    DB_SSL_CLIENT_CERT: Optional[str] = None
    DB_SSL_CLIENT_KEY: Optional[str] = None

    # Redis Broker & Cache
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "CELERY_BROKER_URL"),
        description="Redis connection URI for Celery tasks and session revocation"
    )
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None

    # Redis TLS & Security
    REDIS_SSL_CERT_REQS: Literal["required", "optional", "none"] = Field(
        default="required",
        description="Verification mode for Redis TLS: required, optional, or none"
    )
    REDIS_SSL_CA_CERTS: Optional[str] = Field(
        default=None,
        description="Path to CA certificate bundle file for verifying Redis server certificate"
    )
    REDIS_SSL_CERTFILE: Optional[str] = Field(
        default=None,
        description="Path to client certificate file for Redis mTLS authentication"
    )
    REDIS_SSL_KEYFILE: Optional[str] = Field(
        default=None,
        description="Path to client private key file for Redis mTLS authentication"
    )
    REDIS_SSL_CHECK_HOSTNAME: bool = Field(
        default=True,
        description="Whether to verify Redis server hostname against certificate SAN/CN"
    )

    # Reverse Proxy & Trusted IPs
    FORWARDED_ALLOW_IPS: str = Field(
        default="127.0.0.1,::1",
        description="Comma-separated trusted proxy IP addresses or CIDR ranges for X-Forwarded-* headers"
    )

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
    ALERTMANAGER_HMAC_SECRET: str = Field(
        default="autoheal_dev_alertmanager_webhook_secret_32chars",
        validation_alias=AliasChoices("ALERTMANAGER_HMAC_SECRET", "ALERTMANAGER_WEBHOOK_SECRET"),
        description="Shared HMAC/Bearer secret between Alertmanager and FastAPI alert webhook"
    )
    METRIC_SCRAPE_INTERVAL_SECONDS: int = 15

    # Recovery Automation Engine
    MAX_RECOVERY_RETRIES: int = 3
    RECOVERY_COOLDOWN_SECONDS: int = 300

    # Demo & Safe Simulation Mode
    DEMO_MODE_ENABLED: bool = Field(
        default=True,
        description="Enable controlled demo fault injection and simulation endpoints"
    )
    RECOVERY_SIMULATION_MODE: bool = Field(
        default=True,
        description="Execute simulated safe recoveries instead of modifying real infrastructure"
    )

    # Controlled Restricted Docker Agent (Phase 16)
    RESTRICTED_DOCKER_AGENT_ENABLED: bool = Field(
        default=False,
        description="Explicit opt-in to enable communication with the restricted Docker agent for designated test containers."
    )
    DOCKER_AGENT_URL: str = Field(
        default="http://localhost:8091",
        description="Base URL of the standalone restricted Docker recovery agent."
    )
    DOCKER_AGENT_SECRET_KEY: str = Field(
        default="autoheal_docker_agent_secret_32chars_min",
        description="Shared secret for signing requests dispatched to the restricted Docker recovery agent."
    )
    DOCKER_AGENT_APPROVED_CONTAINERS: List[str] = Field(
        default_factory=lambda: ["autoheal_test_service", "test-service"],
        description="Strict allowlist of container names permitted for controlled recovery operations."
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.APP_ENV in ("production", "staging"):
            if self.FORWARDED_ALLOW_IPS.strip() in ("*", "'*'", '"*"'):
                raise ValueError(
                    "Wildcard FORWARDED_ALLOW_IPS ('*') is strictly prohibited in production. "
                    "Configure explicit trusted reverse proxy IP addresses or CIDR blocks."
                )
            if self.REDIS_SSL_CERT_REQS == "none":
                raise ValueError(
                    "Disabling Redis TLS certificate verification ('none') is strictly prohibited in production or staging."
                )
            if not self.REDIS_SSL_CHECK_HOSTNAME:
                raise ValueError(
                    "Disabling Redis TLS hostname verification is strictly prohibited in production or staging."
                )
            if self.DB_SSL_MODE == "disable":
                raise ValueError(
                    "Disabling database SSL ('disable') is strictly prohibited in production or staging."
                )
            insecure_hmac_defaults = {
                "autoheal_alertmanager_webhook_hmac_secret_key_12345",
                "autoheal_dev_alertmanager_webhook_secret_32chars",
                "",
            }
            if not self.ALERTMANAGER_HMAC_SECRET or self.ALERTMANAGER_HMAC_SECRET in insecure_hmac_defaults:
                raise ValueError(
                    "ALERTMANAGER_HMAC_SECRET is missing or using an insecure default value. "
                    "In production and staging environments, a dedicated secret must be provided via the "
                    "ALERTMANAGER_HMAC_SECRET environment variable."
                )
            insecure_secret_defaults = {
                "autoheal_insecure_dev_secret_change_in_production_1234567890",
                "change_me",
                "secret",
                "",
            }
            if not self.SECRET_KEY or self.SECRET_KEY in insecure_secret_defaults or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "SECRET_KEY is missing, too short (must be >= 32 characters), or using an insecure default value. "
                    "In production and staging environments, a dedicated secret must be provided via the SECRET_KEY environment variable."
                )
            if self.APP_ENV == "production" and "DEMO_MODE_ENABLED" not in self.model_fields_set:
                self.DEMO_MODE_ENABLED = False
        return self


@lru_cache()
def get_settings() -> Settings:
    """
    Returns cached Settings singleton instance.
    """
    return Settings()
