"""
AutoHeal DevOps — Service Level Objective (SLO) & Operational Metrics Schemas
"""

from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class SLOMetricItem(BaseModel):
    """Individual operational SLO / SLA metric."""
    name: str = Field(..., description="Human-readable SLO title")
    metric_key: str = Field(..., description="Unique slug for the metric")
    current_value: float = Field(..., description="Calculated or measured value")
    target_value: float = Field(..., description="Target threshold")
    unit: str = Field(..., description="Unit of measurement: s, ms, %")
    status: Literal["compliant", "at_risk", "breached"] = Field(
        ..., description="Compliance status against target"
    )
    source: Literal["MEASURED", "CALCULATED", "SYNTHETIC_DEMO"] = Field(
        ..., description="Provenance of metric value"
    )
    description: str
    sample_count: int = Field(default=0, description="Number of observed records")


class SLOSummaryResponse(BaseModel):
    """Aggregate SLO performance scorecard for pilot teams."""
    organization_id: str
    period: str
    overall_compliance_percent: float
    overall_status: Literal["compliant", "at_risk", "breached"]
    metrics: List[SLOMetricItem]
    calculated_at: datetime
