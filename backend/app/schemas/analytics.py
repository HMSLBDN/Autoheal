"""
AutoHeal DevOps — Analytics Summary Pydantic Schemas
Strictly matching frontend contracts in types/index.ts and lib/api/resources.ts
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class AnalyticsHistoryPoint(BaseModel):
    """Time-series point for incident/recovery frequency and availability."""
    date: str
    incidents: int
    recoveries: int
    availability: float


class AnalyticsSummaryResponse(BaseModel):
    """Matches frontend AnalyticsSummary interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    detection_latency_seconds: float = Field(..., serialization_alias="detectionLatencySeconds")
    recovery_duration_minutes: float = Field(..., serialization_alias="recoveryDurationMinutes")
    recovery_success_rate: float = Field(..., serialization_alias="recoverySuccessRate")
    false_positive_rate: Optional[float] = Field(None, serialization_alias="falsePositiveRate")
    operator_rejection_rate: Optional[float] = Field(None, serialization_alias="operatorRejectionRate")
    availability: float
    incident_count: int = Field(..., serialization_alias="incidentCount")
    history: List[AnalyticsHistoryPoint] = Field(default_factory=list)
