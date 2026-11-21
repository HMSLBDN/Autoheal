"""
AutoHeal DevOps — Phase 14 Experiment & Benchmark Pydantic Schemas
Strictly matching frontend contracts and statistical evaluation requirements.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

ScenarioType = Literal[
    "healthy_baseline",
    "service_unavailable",
    "high_error_rate",
    "resource_exhaustion",
    "repeated_alerts",
    "verification_failure",
    "recovery_verification_failure",
    "unauthorized_recovery",
    "unapproved_recovery",
]

ExperimentStatusType = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "cancelled",
]

EvidenceClassificationType = Literal[
    "MEASURED",
    "CALCULATED",
    "SYNTHETIC",
    "SIMULATED",
]


class ExperimentCreateRequest(BaseModel):
    """Payload to configure a new reproducible experiment."""
    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name of the experiment")
    description: Optional[str] = Field(default="", description="Detailed objective and hypothesis")
    scenario_type: ScenarioType = Field(..., description="Deterministic benchmark scenario")
    recovery_enabled: bool = Field(default=True, description="Enable simulated autonomous recovery")
    target_service_id: str = Field(default="checkout-api", description="Service under evaluation")
    number_of_runs: int = Field(default=5, ge=1, le=20, description="Repeated run count for statistical confidence")
    random_seed: int = Field(default=42, ge=0, description="Deterministic pseudo-random seed")
    configuration: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom scenario knobs")
    test_conditions: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Environmental test conditions")


class ExperimentRunResponse(BaseModel):
    """Detailed response for an individual experiment run."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    experiment_id: str
    run_number: int
    status: ExperimentStatusType
    recovery_enabled: bool
    seed: int

    fault_injected_at: Optional[datetime] = None
    detected_at: Optional[datetime] = None
    recovery_started_at: Optional[datetime] = None
    recovery_completed_at: Optional[datetime] = None
    health_restored_at: Optional[datetime] = None

    detection_latency_ms: Optional[float] = None
    recovery_duration_ms: Optional[float] = None
    total_outage_duration_ms: Optional[float] = None

    recovery_attempted: bool
    recovery_verified: bool
    recovery_success: bool
    is_false_positive: bool
    safety_compliant: bool
    escalated: bool

    incident_id: Optional[str] = None
    recovery_action_id: Optional[str] = None
    evidence_classification: EvidenceClassificationType = "SIMULATED"

    telemetry_samples: List[Dict[str, Any]] = Field(default_factory=list)
    execution_log: List[Dict[str, Any]] = Field(default_factory=list)
    error_message: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class ExperimentResponse(BaseModel):
    """Summary and details for an experiment suite."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: uuid.UUID
    created_by_user_id: Optional[uuid.UUID] = None
    name: str
    description: str
    scenario_type: str
    execution_mode: str
    recovery_enabled: bool
    target_service_id: str
    number_of_runs: int
    random_seed: int
    configuration: Dict[str, Any]
    test_conditions: Dict[str, Any]
    status: ExperimentStatusType
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results_summary: Dict[str, Any] = Field(default_factory=dict)
    runs_count: int = 0
    runs: Optional[List[ExperimentRunResponse]] = None
    created_at: datetime
    updated_at: datetime


class MetricDistribution(BaseModel):
    """Statistical summary of a scalar metric with honest sample size awareness."""
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    std_dev: Optional[float] = None
    p95: Optional[float] = None
    sample_count: int = 0
    small_sample_size: bool = False
    unit: str = "ms"
    classification: EvidenceClassificationType = "MEASURED"


class ExperimentAnalyticsResponse(BaseModel):
    """Aggregated statistical evaluation for an experiment across all its runs."""
    experiment_id: str
    scenario_type: str
    recovery_enabled: bool
    total_runs: int
    completed_runs: int

    detection_latency: MetricDistribution
    recovery_duration: MetricDistribution
    total_outage_duration: MetricDistribution

    recovery_success_rate: float = Field(..., description="Percentage of recovery attempts verified healthy (0-100%)")
    false_positive_rate: float = Field(..., description="Percentage of healthy states flagged as incidents (0-100%)")
    safety_compliance_rate: float = Field(..., description="Percentage of executions strictly safety compliant (0-100%)")
    escalation_rate: float = Field(..., description="Percentage of runs escalating to operator (0-100%)")

    evidence_classification: EvidenceClassificationType = "SIMULATED"
    sample_size_warning: Optional[str] = None


class ExperimentComparisonResponse(BaseModel):
    """Direct comparison between Recovery Enabled and Recovery Disabled modes."""
    scenario_type: str
    random_seed: int
    enabled_experiment: Optional[ExperimentAnalyticsResponse] = None
    disabled_experiment: Optional[ExperimentAnalyticsResponse] = None

    outage_reduction_ms: Optional[float] = None
    outage_reduction_percentage: Optional[float] = None
    mttr_improvement_percentage: Optional[float] = None
    is_statistically_significant: bool = False
    confidence_note: str
    evidence_classification: EvidenceClassificationType = "SIMULATED"
