"""
AutoHeal DevOps — Incident, Evidence & Event Pydantic Schemas
Strictly matching frontend contracts in types/index.ts and lib/api/resources.ts
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

SeverityType = Literal["critical", "high", "medium", "low"]
IncidentStatusType = Literal[
    "new",
    "acknowledged",
    "investigation",
    "diagnosis",
    "approval_pending",
    "recovery_in_progress",
    "recovery_verification",
    "resolved",
    "failed_recovery",
    "escalated",
    "reopened",
    # Legacy / UI aliases
    "open",
    "investigating",
    "recovering",
]
EvidenceKindType = Literal["metric", "log", "deployment", "health_check"]
EventToneType = Literal["neutral", "warning", "success"]


class IncidentEvidenceResponse(BaseModel):
    """Matches frontend IncidentEvidence interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    kind: EvidenceKindType
    title: str
    detail: str
    timestamp: str


class IncidentEventResponse(BaseModel):
    """Matches frontend IncidentEvent interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    label: str
    detail: str
    timestamp: str
    tone: EventToneType


class IncidentResponse(BaseModel):
    """Matches frontend Incident interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    title: str
    severity: SeverityType
    status: IncidentStatusType
    detected_at: str = Field(..., serialization_alias="detectedAt")
    recovery_status: str = Field(..., serialization_alias="recoveryStatus")
    error_rate: float = Field(..., serialization_alias="errorRate")
    threshold: float
    probable_cause: str = Field(..., serialization_alias="probableCause")
    recommended_action: str = Field(..., serialization_alias="recommendedAction")
    evidence: List[IncidentEvidenceResponse] = Field(default_factory=list)
    events: List[IncidentEventResponse] = Field(default_factory=list)


class IncidentTransitionRequest(BaseModel):
    """Request payload to advance an incident through its lifecycle."""
    new_status: str = Field(..., description="Target lifecycle state")
    reason: str = Field(..., min_length=3, description="Justification for state mutation")
    evidence_id: Optional[str] = Field(None, description="Optional attached evidence ID")
    sign_off: Optional[bool] = Field(False, description="Explicit operator sign-off for resolution")


class IncidentTransitionResponse(BaseModel):
    """Immutable audit record for an incident lifecycle state mutation."""
    id: str
    incident_id: str
    actor_email: str
    actor_role: str
    previous_state: str
    new_state: str
    reason: str
    evidence_id: Optional[str] = None
    sign_off: bool
    created_at: str
