"""
AutoHeal DevOps — Recovery Policy Schemas
Pydantic schemas for policy governance and evaluation endpoints.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class PolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    service_id: str = Field(..., serialization_alias="serviceId")
    action: str
    approval_required: bool = Field(..., serialization_alias="approvalRequired")
    cooldown_seconds: int = Field(..., serialization_alias="cooldownSeconds")
    max_retries: int = Field(..., serialization_alias="maxRetries")
    is_active: bool = Field(..., serialization_alias="isActive")


class PolicyUpdateRequest(BaseModel):
    approval_required: Optional[bool] = None
    cooldown_seconds: Optional[int] = Field(None, ge=10, le=86400)
    max_retries: Optional[int] = Field(None, ge=1, le=10)
    is_active: Optional[bool] = None


class PolicyEvaluationRequest(BaseModel):
    service_id: str = Field(..., description="Target service UUID")
    action: str = Field(..., description="Operation to evaluate")
    agent_id: Optional[str] = Field(None, description="Optional agent UUID to check compatibility")


class PolicyEvaluationResponse(BaseModel):
    allowed: bool
    requires_approval: bool = Field(..., serialization_alias="requiresApproval")
    reason: str
    cooldown_remaining_seconds: int = Field(0, serialization_alias="cooldownRemainingSeconds")
    retry_count: int = Field(0, serialization_alias="retryCount")
    max_retries: int = Field(3, serialization_alias="maxRetries")
