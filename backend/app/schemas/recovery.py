"""
AutoHeal DevOps — Recovery Action & Result Pydantic Schemas
Strictly matching frontend contracts in types/index.ts and lib/api/resources.ts
"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

RecoveryStatusType = Literal[
    "pending_approval",
    "approved",
    "running",
    "completed",
    "failed",
    "rejected",
]
VerificationType = Literal["pending", "passed", "failed", "not_started"]


class RecoveryResultResponse(BaseModel):
    """Matches frontend RecoveryResult interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    verified: bool
    summary: str
    completed_at: str = Field(..., serialization_alias="completedAt")


class RecoveryActionResponse(BaseModel):
    """Matches frontend RecoveryAction interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    incident_id: str = Field(..., serialization_alias="incidentId")
    service_name: str = Field(..., serialization_alias="serviceName")
    action: str
    status: RecoveryStatusType
    approval_required: bool = Field(..., serialization_alias="approvalRequired")
    requested_by: str = Field(..., serialization_alias="requestedBy")
    requested_at: str = Field(..., serialization_alias="requestedAt")
    duration_seconds: Optional[int] = Field(None, serialization_alias="durationSeconds")
    verification: VerificationType
    result: Optional[RecoveryResultResponse] = None


class RecoveryRejectRequest(BaseModel):
    """Optional request payload when rejecting a recovery action."""
    reason: Optional[str] = Field(None, max_length=500, description="Operator rejection reason")


class RecoveryTriggerRequest(BaseModel):
    """Optional request payload when requesting a controlled recovery."""
    action: Optional[str] = Field(None, max_length=255, description="Custom allowlisted action key")
