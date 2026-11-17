"""
AutoHeal DevOps — Restricted Infrastructure Agent Models
Pydantic schemas for agent registration, action dispatch envelopes, and execution receipts.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AgentStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ActionExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class AgentRegistration(BaseModel):
    """Registration payload presented by an infrastructure agent to the control plane."""
    agent_id: str = Field(..., description="Unique UUID of the remote infrastructure agent")
    hostname: str = Field(..., description="Hostname of the node running the agent")
    ip_address: str = Field(..., description="Private IP address of the agent node")
    version: str = Field("1.0.0", description="Agent release version")
    supported_actions: List[str] = Field(default_factory=list, description="Allowlisted actions supported by this node")
    public_key_fingerprint: str = Field(..., description="SHA-256 fingerprint of the agent's public key or shared secret")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentHeartbeat(BaseModel):
    """Periodic health ping sent by the agent to the control plane."""
    agent_id: str
    status: AgentStatus = AgentStatus.ONLINE
    active_actions_count: int = 0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ActionRequest(BaseModel):
    """
    Cryptographically signed command envelope dispatched from Control Plane to Agent.
    Strictly forbids raw shell or arbitrary script execution.
    """
    action_id: str = Field(..., description="Unique ID for this action execution")
    service_id: str = Field(..., description="Target service UUID")
    service_name: str = Field(..., description="Target service name")
    action_type: str = Field(..., description="Allowlisted operation (e.g. restart_service, scale_service)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated typed arguments for the operation")
    timeout_seconds: int = Field(30, ge=1, le=120, description="Max execution time before hard kill")
    nonce: str = Field(..., description="Cryptographic single-use nonce to prevent replay attacks")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Generation timestamp")
    signature: str = Field("", description="HMAC-SHA256 signature of canonical payload")

    @field_validator("action_type")
    def validate_action_type(cls, v: str) -> str:
        clean = v.strip().lower()
        if not clean.replace("_", "").isalnum():
            raise ValueError("Action type must contain only alphanumeric characters and underscores.")
        return clean


class ActionResult(BaseModel):
    """
    Evidence and cryptographic receipt returned by the agent upon action completion.
    """
    action_id: str
    agent_id: str
    status: ActionExecutionStatus
    exit_code: int = Field(0, description="Process exit code (0 for clean execution)")
    duration_ms: int = Field(..., ge=0, description="Elapsed execution duration in milliseconds")
    stdout_summary: str = Field("", max_length=4096, description="Sanitized, truncated standard output")
    stderr_summary: str = Field("", max_length=4096, description="Sanitized, truncated error output")
    evidence_receipt_hash: str = Field(..., description="Cryptographic SHA-256 hash/signature of execution evidence")
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
