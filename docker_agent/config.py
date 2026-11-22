"""
Restricted Docker Agent — Configuration Module
Loads settings from environment variables with strict security validation.
"""

import os
import re
from typing import Set


class AgentSettings:
    """Agent runtime settings with strict credential validation and mTLS support."""

    AGENT_ID: str = os.getenv("DOCKER_AGENT_ID", "docker-agent-restricted-01")
    AGENT_HOST: str = os.getenv("DOCKER_AGENT_HOST", "0.0.0.0")
    AGENT_PORT: int = int(os.getenv("DOCKER_AGENT_PORT", "8091"))
    AGENT_SECRET_KEY: str = os.getenv("DOCKER_AGENT_SECRET_KEY", "")

    # Approved test containers ONLY. Any container outside this set is rejected.
    APPROVED_CONTAINERS: Set[str] = {
        c.strip()
        for c in os.getenv(
            "DOCKER_AGENT_APPROVED_CONTAINERS", "autoheal_test_service,test-service"
        ).split(",")
        if c.strip()
    }

    # Docker daemon / Proxy connection
    DOCKER_SOCKET_PATH: str = os.getenv("DOCKER_SOCKET_PATH", "")
    DOCKER_HOST_URL: str = os.getenv("DOCKER_HOST_URL", "https://autoheal_socket_proxy:8443")

    # Mutual TLS (mTLS) Certificate Configuration
    PROXY_CA_CERT_PATH: str = os.getenv("PROXY_CA_CERT_PATH", "/etc/ssl/certs/autoheal/ca.crt")
    AGENT_CLIENT_CERT_PATH: str = os.getenv("AGENT_CLIENT_CERT_PATH", "/etc/ssl/certs/autoheal/agent.crt")
    AGENT_CLIENT_KEY_PATH: str = os.getenv("AGENT_CLIENT_KEY_PATH", "/etc/ssl/certs/autoheal/agent.key")

    # Security thresholds
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    MAX_TIMESTAMP_DRIFT_SECONDS: int = int(os.getenv("MAX_TIMESTAMP_DRIFT_SECONDS", "300"))
    REPLAY_CACHE_TTL_SECONDS: int = int(os.getenv("REPLAY_CACHE_TTL_SECONDS", "300"))

    # Simulation mode lock (defaults to true; blocks real destructive recovery operations)
    SIMULATION_MODE: bool = os.getenv(
        "DOCKER_AGENT_SIMULATION_MODE",
        os.getenv("RECOVERY_SIMULATION_MODE", "true"),
    ).lower() in ("true", "1", "yes")
    DOCKER_AGENT_SIMULATION_MODE: bool = SIMULATION_MODE

    # Audit authentication requirement
    REQUIRE_AUTH_FOR_AUDIT: bool = os.getenv(
        "DOCKER_AGENT_REQUIRE_AUTH_FOR_AUDIT", "false"
    ).lower() in ("true", "1", "yes")

    # Mock fallback flag (allows unit/integration testing when Docker daemon is unavailable)
    ENABLE_MOCK_FALLBACK: bool = os.getenv("DOCKER_AGENT_ENABLE_MOCK_FALLBACK", "true").lower() in (
        "true",
        "1",
        "yes",
    )

    def validate_security(self=None) -> None:
        """
        Validates security configurations:
        - In production, staging, or whenever enforcement is triggered, default secrets
          or secrets < 32 characters are strictly forbidden.
        - Rejects predictable default tokens.
        - Raises ValueError if insecure configuration is detected.
        """
        env = os.getenv("APP_ENV", "development").lower()
        key = getattr(self, "AGENT_SECRET_KEY", None) or AgentSettings.AGENT_SECRET_KEY

        # In production/staging, strict 32+ character requirement and pattern rejection
        if env in ("production", "staging"):
            if not key:
                raise ValueError("DOCKER_AGENT_SECRET_KEY must be set in production and staging environments.")
            if len(key) < 32:
                raise ValueError("DOCKER_AGENT_SECRET_KEY must be at least 32 characters long.")
            
            insecure_patterns = [
                r"default",
                r"change_me",
                r"secret_key_prod",
                r"autoheal_agent_default",
                r"autoheal_docker_agent_secret",
            ]
            for pattern in insecure_patterns:
                if re.search(pattern, key, re.IGNORECASE):
                    raise ValueError(
                        f"Insecure default DOCKER_AGENT_SECRET_KEY or predictable pattern '{pattern}' detected. "
                        "Refusing startup in production mode."
                    )
        elif key and len(key) < 16:
            raise ValueError("DOCKER_AGENT_SECRET_KEY is too short (minimum 16 characters in dev, 32 in prod).")

    def __repr__(self) -> str:
        """Redact sensitive credentials in string representations."""
        return (
            f"<AgentSettings AGENT_ID={self.AGENT_ID} "
            f"AGENT_HOST={self.AGENT_HOST}:{self.AGENT_PORT} "
            f"SIMULATION_MODE={self.SIMULATION_MODE} "
            f"DOCKER_HOST_URL={self.DOCKER_HOST_URL} "
            f"AGENT_SECRET_KEY=[REDACTED]>"
        )


settings = AgentSettings()
