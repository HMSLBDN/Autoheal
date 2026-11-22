"""
Restricted Docker Agent — Request & Response Schemas
Strongly typed Pydantic models for action requests, execution receipts, and health queries.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ActionType(str, Enum):
    INSPECT_CONTAINER = "inspect_container"
    GET_CONTAINER_STATE = "get_container_state"
    GET_CONTAINER_HEALTH = "get_container_health"
    RESTART_CONTAINER = "restart_container"
    VERIFY_CONTAINER_HEALTH = "verify_container_health"


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


class ActionExecutionRequest(BaseModel):
    """
    Cryptographically signed command envelope dispatched to the Restricted Docker Agent.
    Strictly forbids raw shell or arbitrary script execution.
    """
    action_id: str = Field(..., description="Unique ID for this action execution")
    target_container: str = Field(..., description="Approved container identifier (e.g. autoheal_test_service)")
    action_type: str = Field(..., description="Allowlisted operation name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Typed parameters for the operation")
    timeout_seconds: int = Field(30, ge=1, le=120, description="Max execution time before hard kill")
    nonce: str = Field(..., description="Cryptographic single-use nonce to prevent replay attacks")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation timestamp")
    signature: str = Field(..., description="HMAC-SHA256 signature of canonical payload")
    correlation_id: Optional[str] = Field(None, description="Distributed tracing correlation ID")

    @field_validator("target_container")
    def validate_container_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Target container identifier cannot be empty.")
        return clean

    @field_validator("action_type")
    def validate_action_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean.replace("_", "").isalnum():
            raise ValueError("Action type must contain only alphanumeric characters and underscores.")
        return clean


class ActionExecutionResponse(BaseModel):
    """
    Evidence and cryptographic receipt returned by the agent upon action completion.
    """
    action_id: str
    target_container: str
    action_type: str
    status: ActionStatus
    exit_code: int = Field(0, description="Process exit code (0 for clean execution)")
    duration_ms: int = Field(..., ge=0, description="Elapsed execution duration in milliseconds")
    stdout: str = Field("", max_length=4096, description="Sanitized, truncated standard output")
    stderr: str = Field("", max_length=4096, description="Sanitized, truncated error output")
    evidence_receipt_hash: str = Field(..., description="Cryptographic SHA-256 hash of execution evidence")
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[str] = None
    is_mocked: bool = Field(False, description="Explicit flag indicating whether execution was mocked or against live Docker socket")


class ContainerStatus(BaseModel):
    """Container inspection and lifecycle status."""
    container_name: str
    status: str = Field(..., description="Container status (e.g. running, exited, paused)")
    state: str = Field(..., description="Container lifecycle state string")
    health: str = Field("unknown", description="Docker health check status (healthy, unhealthy, starting, none)")
    restart_count: int = Field(0, description="Cumulative container restart count")
    uptime_seconds: int = Field(0, description="Uptime in seconds")
    image: str = Field("", description="Container image repository and tag")
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_mocked: bool = Field(False, description="True if response generated from mock engine")


class AgentHealthResponse(BaseModel):
    """Agent daemon health status."""
    status: str = "healthy"
    agent_id: str
    version: str = "0.1.0"
    uptime_seconds: int = 0
    docker_available: bool = False
    approved_containers: List[str] = []
    allowed_operations: List[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
