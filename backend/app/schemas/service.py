"""
AutoHeal DevOps — Service & Telemetry Pydantic Schemas
Strictly matching frontend contracts in types/index.ts and lib/api/resources.ts
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

ServiceStatusType = Literal["healthy", "degraded", "critical"]


class ServiceResponse(BaseModel):
    """Matches frontend Service interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    environment: str
    status: ServiceStatusType
    availability: float
    error_rate: float = Field(..., serialization_alias="errorRate")
    latency_ms: int = Field(..., serialization_alias="latencyMs")
    last_checked: str = Field(..., serialization_alias="lastChecked")


class MetricPoint(BaseModel):
    """Time-series point for metrics chart."""
    time: str
    value: float


class ServiceMetricsResponse(BaseModel):
    """Matches frontend ServiceMetrics interface."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    service_id: str = Field(..., serialization_alias="serviceId")
    sampled_at: str = Field(..., serialization_alias="sampledAt")
    cpu_percent: float = Field(..., serialization_alias="cpuPercent")
    memory_percent: float = Field(..., serialization_alias="memoryPercent")
    request_rate: float = Field(..., serialization_alias="requestRate")
    error_rate: float = Field(..., serialization_alias="errorRate")
    latency_ms: int = Field(..., serialization_alias="latencyMs")
    availability: float
    history: List[MetricPoint]
