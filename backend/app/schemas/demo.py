"""
AutoHeal DevOps — Demo Controls Pydantic Schemas
Defines request and response payloads for controlled failure injection,
safe environment resets, and deterministic alert simulations.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class DemoFaultRequest(BaseModel):
    """Payload for triggering controlled fault injection in demo mode."""
    service_name: str = Field(
        default="checkout-api",
        description="Target microservice name (checkout-api, customer-web, payments-api, etc.)"
    )
    fault_type: Literal[
        "service_down",
        "http_500",
        "high_latency",
        "degraded",
        "cpu_saturation",
        "memory_leak",
    ] = Field(
        default="http_500",
        description="Controlled failure scenario to execute"
    )
    error_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Target HTTP error rate ratio (0.0 = 0%, 1.0 = 100%)"
    )
    latency_ms: Optional[int] = Field(
        default=None,
        ge=0,
        le=30000,
        description="Target HTTP response latency in milliseconds"
    )
    cpu_usage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Target simulated CPU utilization ratio"
    )


class DemoFaultResponse(BaseModel):
    """Response confirming controlled fault injection."""
    status: str
    service_name: str
    fault_type: str
    message: str
    metrics: Dict[str, Any]
    timestamp: str


class DemoResetRequest(BaseModel):
    """Payload for restoring demo environment to healthy state."""
    service_name: Optional[str] = Field(
        default=None,
        description="Specific service to restore, or null to restore all monitored services"
    )


class DemoResetResponse(BaseModel):
    """Response confirming health restoration."""
    status: str
    restored_services: List[str]
    message: str
    timestamp: str


class DemoServiceStatus(BaseModel):
    """Snapshot of monitored service status in demo environment."""
    service_name: str
    status: str
    availability: float
    error_rate: float
    latency_ms: int
    chaos_endpoint_reachable: bool


class DemoStatusResponse(BaseModel):
    """Overall demo environment configuration and microservice status."""
    demo_mode_enabled: bool
    recovery_simulation_mode: bool
    environment: str
    services: List[DemoServiceStatus]


class DemoSimulateAlertRequest(BaseModel):
    """Payload for directly dispatching a verified Alertmanager alert into the incident pipeline."""
    service_name: str = Field(
        default="checkout-api",
        description="Monitored service receiving the alert"
    )
    alertname: str = Field(
        default="HighErrorRate",
        description="Prometheus alert rule identifier"
    )
    severity: Literal["critical", "high", "medium", "low"] = Field(
        default="critical",
        description="Alert severity tier"
    )
    summary: Optional[str] = Field(
        default=None,
        description="High-level incident summary"
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed alert description and telemetry context"
    )
    probable_cause: Optional[str] = Field(
        default=None,
        description="Known probable cause for deterministic validation"
    )
    recommended_action: Optional[str] = Field(
        default=None,
        description="Recommended recovery action from the allowlist"
    )
    auto_request_recovery: bool = Field(
        default=True,
        description="If True, automatically enqueue the recommended action in pending_approval status"
    )


class DemoSimulateAlertResponse(BaseModel):
    """Response after processing simulated alert through the full pipeline."""
    status: str
    incident_id: Optional[str]
    recovery_id: Optional[str]
    recommended_action: Optional[str]
    message: str
