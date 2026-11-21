"""
AutoHeal DevOps — Infrastructure Agent Schemas
Pydantic contracts for agent lifecycle management and status reporting.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AgentResponse(BaseModel):
    """Public representation of an infrastructure agent."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    name: str
    hostname: str
    ip_address: str = Field(..., serialization_alias="ipAddress")
    environment: str
    status: str
    version: str
    capabilities: List[str]
    public_key_fingerprint: str = Field(..., serialization_alias="publicKeyFingerprint")
    last_heartbeat: str = Field(..., serialization_alias="lastHeartbeat")
    created_at: str = Field(..., serialization_alias="createdAt")


class AgentRegisterRequest(BaseModel):
    """Payload to register a new restricted agent on a compute node."""
    name: str = Field(..., min_length=2, max_length=100)
    hostname: str = Field(..., min_length=2, max_length=100)
    ip_address: str = Field(..., min_length=7, max_length=50)
    environment: str = Field("production", max_length=50)
    capabilities: List[str] = Field(
        default_factory=lambda: ["restart_service", "scale_service", "clear_cache", "health_check"]
    )
    public_key_fingerprint: Optional[str] = None


class AgentRegisterResponse(BaseModel):
    """Response returned upon successful agent registration."""
    agent: AgentResponse
    agent_secret: str = Field(..., description="Secret token used by the agent to sign heartbeats and receipts")
    secret_key: Optional[str] = Field(None, description="Convenience alias for agent_secret")


class AgentHeartbeatRequest(BaseModel):
    """Telemetry heartbeat dispatched periodically by the agent."""
    status: str = Field("online")
    cpu_percent: float = Field(0.0, ge=0.0, le=100.0)
    memory_percent: float = Field(0.0, ge=0.0, le=100.0)
    active_actions_count: int = Field(0, ge=0)


class AgentMessageResponse(BaseModel):
    message: str
    status: str
