"""
AutoHeal DevOps — AI Intelligence, Prediction & Risk Scoring Schemas
Pydantic schemas for predictive detection, anomalies, risk scoring,
correlation, and enhanced AI incident diagnosis.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class AnomalyResponse(BaseModel):
    """Detected metric anomaly."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    metric_name: str = Field(..., serialization_alias="metricName")
    current_value: float = Field(..., serialization_alias="currentValue")
    baseline_value: float = Field(..., serialization_alias="baselineValue")
    z_score: float = Field(..., serialization_alias="zScore")
    anomaly_score: float = Field(..., serialization_alias="anomalyScore")
    severity: Literal["informational", "low", "medium", "high", "critical"]
    status: Literal["detected", "correlated", "resolved", "suppressed"]
    details: str
    detected_at: str = Field(..., serialization_alias="detectedAt")
    created_at: str = Field(..., serialization_alias="createdAt")


class PredictionResponse(BaseModel):
    """Predictive time-series incident forecast."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    metric_name: str = Field(..., serialization_alias="metricName")
    current_value: float = Field(..., serialization_alias="currentValue")
    predicted_value: float = Field(..., serialization_alias="predictedValue")
    threshold_value: float = Field(..., serialization_alias="thresholdValue")
    prediction_horizon_minutes: int = Field(..., serialization_alias="predictionHorizonMinutes")
    risk_level: Literal["informational", "low", "medium", "high", "critical"] = Field(..., serialization_alias="riskLevel")
    anomaly_probability: float = Field(..., serialization_alias="anomalyProbability")
    algorithm: str
    supporting_evidence: List[str] = Field(default_factory=list, serialization_alias="supportingEvidence")
    recommended_preventive_action: str = Field(..., serialization_alias="recommendedPreventiveAction")
    predicted_at: str = Field(..., serialization_alias="predictedAt")
    target_time: str = Field(..., serialization_alias="targetTime")


class RiskFactor(BaseModel):
    """Explainable component contributing to service risk score."""
    factor: str
    weight: float
    description: str
    severity: Literal["low", "medium", "high", "critical"]


class ServiceRiskResponse(BaseModel):
    """Composite health risk score for a service."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    risk_score: float = Field(..., serialization_alias="riskScore")
    risk_category: Literal["low", "moderate", "high", "critical"] = Field(..., serialization_alias="riskCategory")
    contributing_factors: List[RiskFactor] = Field(default_factory=list, serialization_alias="contributingFactors")
    cpu_trend: str = Field(..., serialization_alias="cpuTrend")
    memory_trend: str = Field(..., serialization_alias="memoryTrend")
    incident_frequency_7d: int = Field(..., serialization_alias="incidentFrequency7d")
    failed_recoveries_count: int = Field(..., serialization_alias="failedRecoveriesCount")
    recent_deployment_flag: bool = Field(..., serialization_alias="recentDeploymentFlag")
    calculated_at: str = Field(..., serialization_alias="calculatedAt")


class IncidentCorrelationItem(BaseModel):
    """Summary of a correlated incident in a group."""
    incident_id: str = Field(..., serialization_alias="incidentId")
    service_name: str = Field(..., serialization_alias="serviceName")
    title: str
    severity: str
    status: str
    detected_at: str = Field(..., serialization_alias="detectedAt")


class IncidentCorrelationGroupResponse(BaseModel):
    """Group of incidents correlated by shared underlying root causes."""
    group_id: str = Field(..., serialization_alias="groupId")
    primary_incident_id: str = Field(..., serialization_alias="primaryIncidentId")
    correlation_type: str = Field(..., serialization_alias="correlationType")
    correlation_score: float = Field(..., serialization_alias="correlationScore")
    explanation: str
    shared_evidence: List[str] = Field(default_factory=list, serialization_alias="sharedEvidence")
    incidents: List[IncidentCorrelationItem] = Field(default_factory=list)
    created_at: str = Field(..., serialization_alias="createdAt")


class DeploymentImpactResponse(BaseModel):
    """Assessment of release deployment temporal impact on service metrics."""
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    release_tag: str = Field(..., serialization_alias="releaseTag")
    deployed_at: str = Field(..., serialization_alias="deployedAt")
    time_since_deployment_minutes: float = Field(..., serialization_alias="timeSinceDeploymentMinutes")
    is_temporally_correlated: bool = Field(..., serialization_alias="isTemporallyCorrelated")
    pre_deployment_metrics: Dict[str, float] = Field(..., serialization_alias="preDeploymentMetrics")
    post_deployment_metrics: Dict[str, float] = Field(..., serialization_alias="postDeploymentMetrics")
    metric_deltas: Dict[str, float] = Field(..., serialization_alias="metricDeltas")
    probable_impact_summary: str = Field(..., serialization_alias="probableImpactSummary")
    recommended_investigation: str = Field(..., serialization_alias="recommendedInvestigation")


class PreventiveRecommendationResponse(BaseModel):
    """Proactive recommendation to avoid outages or resource exhaustion."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    title: str
    description: str
    priority: Literal["critical", "high", "medium", "low"]
    risk_level: Literal["critical", "high", "medium", "low"] = Field(..., serialization_alias="riskLevel")
    category: str
    supporting_evidence: List[str] = Field(default_factory=list, serialization_alias="supportingEvidence")
    expected_benefit: str = Field(..., serialization_alias="expectedBenefit")
    suggested_action: str = Field(..., serialization_alias="suggestedAction")
    status: Literal["open", "acknowledged", "dismissed", "applied"]
    created_at: str = Field(..., serialization_alias="createdAt")


class SimilarIncidentResponse(BaseModel):
    """Historical incident with comparable failure indicators."""
    incident_id: str = Field(..., serialization_alias="incidentId")
    title: str
    service_name: str = Field(..., serialization_alias="serviceName")
    similarity_score: float = Field(..., serialization_alias="similarityScore")
    previous_root_cause: str = Field(..., serialization_alias="previousRootCause")
    previous_recovery_action: str = Field(..., serialization_alias="previousRecoveryAction")
    recovery_outcome: str = Field(..., serialization_alias="recoveryOutcome")
    resolution_duration_minutes: Optional[float] = Field(None, serialization_alias="resolutionDurationMinutes")
    detected_at: str = Field(..., serialization_alias="detectedAt")


class IncidentAnalysisResponse(BaseModel):
    """Enhanced deep AI diagnosis for a specific incident."""
    incident_id: str = Field(..., serialization_alias="incidentId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    summary: str
    probable_root_cause: str = Field(..., serialization_alias="probableRootCause")
    severity: Literal["critical", "high", "medium", "low"]
    risk_level: Literal["critical", "high", "medium", "low"] = Field(..., serialization_alias="riskLevel")
    confidence_score: float = Field(..., serialization_alias="confidenceScore")
    affected_components: List[str] = Field(default_factory=list, serialization_alias="affectedComponents")
    confirmed_evidence: List[str] = Field(default_factory=list, serialization_alias="confirmedEvidence")
    unverified_hypotheses: List[str] = Field(default_factory=list, serialization_alias="unverifiedHypotheses")
    potential_business_impact: str = Field(..., serialization_alias="potentialBusinessImpact")
    suggested_investigation_steps: List[str] = Field(default_factory=list, serialization_alias="suggestedInvestigationSteps")
    recommended_recovery_action: str = Field(..., serialization_alias="recommendedRecoveryAction")
    alternative_recovery_action: Optional[str] = Field(None, serialization_alias="alternativeRecoveryAction")
    prevention_recommendations: List[str] = Field(default_factory=list, serialization_alias="preventionRecommendations")
    verification_requirements: List[str] = Field(default_factory=list, serialization_alias="verificationRequirements")
    similar_historical_incidents: List[SimilarIncidentResponse] = Field(default_factory=list, serialization_alias="similarHistoricalIncidents")
    correlated_incident_ids: List[str] = Field(default_factory=list, serialization_alias="correlatedIncidentIds")
    deployment_impact: Optional[DeploymentImpactResponse] = Field(None, serialization_alias="deploymentImpact")
    provider_source: Literal["gemini", "heuristic_fallback"] = Field("heuristic_fallback", serialization_alias="providerSource")
    analyzed_at: str = Field(..., serialization_alias="analyzedAt")


class ModelEvaluationMetricResponse(BaseModel):
    """Quality and benchmark evaluation for an AI or statistical model."""
    model_name: str = Field(..., serialization_alias="modelName")
    evaluation_type: str = Field(..., serialization_alias="evaluationType")
    dataset_name: str = Field(..., serialization_alias="datasetName")
    is_synthetic: bool = Field(..., serialization_alias="isSynthetic")
    sample_count: int = Field(..., serialization_alias="sampleCount")
    precision: float
    recall: float
    f1_score: float = Field(..., serialization_alias="f1Score")
    false_positive_rate: float = Field(..., serialization_alias="falsePositiveRate")
    false_negative_rate: float = Field(..., serialization_alias="falseNegativeRate")
    mean_absolute_error: Optional[float] = Field(None, serialization_alias="meanAbsoluteError")
    mean_latency_ms: float = Field(..., serialization_alias="meanLatencyMs")
    evaluated_at: str = Field(..., serialization_alias="evaluatedAt")


class AnomalyDetectRequest(BaseModel):
    """Payload to trigger anomaly evaluation for a metric."""
    model_config = ConfigDict(populate_by_name=True)

    service_id: str = Field(..., validation_alias="serviceId")
    service_name: Optional[str] = Field(None, validation_alias="serviceName")
    metric_name: str = Field(..., validation_alias="metricName")
    current_value: float = Field(..., validation_alias="currentValue")
    history: List[float] = Field(default_factory=list)


class RecommendationStatusUpdateRequest(BaseModel):
    """Payload to update recommendation status."""
    status: Literal["open", "acknowledged", "dismissed", "applied"]


class IntelligenceOverviewResponse(BaseModel):
    """High-level summary for the AI Intelligence Dashboard overview."""
    active_predictions_count: int = Field(..., serialization_alias="activePredictionsCount")
    detected_anomalies_count: int = Field(..., serialization_alias="detectedAnomaliesCount")
    high_risk_services_count: int = Field(..., serialization_alias="highRiskServicesCount")
    open_recommendations_count: int = Field(..., serialization_alias="openRecommendationsCount")
    predictions: List[PredictionResponse] = Field(default_factory=list)
    anomalies: List[AnomalyResponse] = Field(default_factory=list)
    top_risk_services: List[ServiceRiskResponse] = Field(default_factory=list, serialization_alias="topRiskServices")
    preventive_recommendations: List[PreventiveRecommendationResponse] = Field(default_factory=list, serialization_alias="preventiveRecommendations")
    recent_correlations: List[IncidentCorrelationGroupResponse] = Field(default_factory=list, serialization_alias="recentCorrelations")
