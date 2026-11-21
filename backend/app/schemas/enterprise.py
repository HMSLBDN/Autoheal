"""
AutoHeal DevOps — Phase 9 Enterprise Schemas
Pydantic v2 validation models for notifications, signed webhooks, incident collaboration,
escalation policies, canary release evaluation, and unified timeline.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


# ==============================================================================
# Notification Channel & Subscription Schemas
# ==============================================================================

class NotificationChannelCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    channel_type: Literal["email", "slack", "teams", "webhook"] = Field(..., alias="channelType")
    is_enabled: bool = Field(False, alias="isEnabled")
    config: Dict[str, Any] = Field(default_factory=dict)
    secret_token: Optional[str] = Field(None, alias="secretToken")
    rate_limit_per_minute: int = Field(30, ge=1, le=300, alias="rateLimitPerMinute")


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    is_enabled: Optional[bool] = Field(None, alias="isEnabled")
    config: Optional[Dict[str, Any]] = None
    secret_token: Optional[str] = Field(None, alias="secretToken")
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=300, alias="rateLimitPerMinute")


class NotificationChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    name: str
    channel_type: str = Field(..., serialization_alias="channelType")
    is_enabled: bool = Field(..., serialization_alias="isEnabled")
    config_masked: Dict[str, Any] = Field(..., serialization_alias="configMasked")
    rate_limit_per_minute: int = Field(..., serialization_alias="rateLimitPerMinute")
    created_at: str = Field(..., serialization_alias="createdAt")
    updated_at: str = Field(..., serialization_alias="updatedAt")


class NotificationSubscriptionCreate(BaseModel):
    channel_id: str = Field(..., alias="channelId")
    event_type: str = Field(..., alias="eventType")
    min_severity: Literal["informational", "low", "medium", "high", "critical"] = Field("medium", alias="minSeverity")
    is_active: bool = Field(True, alias="isActive")


class NotificationSubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    channel_id: str = Field(..., serialization_alias="channelId")
    event_type: str = Field(..., serialization_alias="eventType")
    min_severity: str = Field(..., serialization_alias="minSeverity")
    is_active: bool = Field(..., serialization_alias="isActive")
    created_at: str = Field(..., serialization_alias="createdAt")


class NotificationDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    channel_id: str = Field(..., serialization_alias="channelId")
    channel_name: str = Field(..., serialization_alias="channelName")
    channel_type: str = Field(..., serialization_alias="channelType")
    incident_id: Optional[str] = Field(None, serialization_alias="incidentId")
    event_type: str = Field(..., serialization_alias="eventType")
    idempotency_key: str = Field(..., serialization_alias="idempotencyKey")
    payload: Dict[str, Any]
    status: Literal["pending", "processing", "delivered", "retrying", "failed", "permanently_failed", "disabled"]
    retry_count: int = Field(..., serialization_alias="retryCount")
    max_retries: int = Field(..., serialization_alias="maxRetries")
    provider_response_code: Optional[int] = Field(None, serialization_alias="providerResponseCode")
    failure_reason: Optional[str] = Field(None, serialization_alias="failureReason")
    delivered_at: Optional[str] = Field(None, serialization_alias="deliveredAt")
    next_retry_at: Optional[str] = Field(None, serialization_alias="nextRetryAt")
    created_at: str = Field(..., serialization_alias="createdAt")


class TestNotificationRequest(BaseModel):
    message: Optional[str] = "AutoHeal DevOps verified test notification signal."


class TestNotificationResponse(BaseModel):
    delivery_id: str = Field(..., serialization_alias="deliveryId")
    status: str
    detail: str


# ==============================================================================
# Webhook Endpoint Schemas (SSRF-Protected)
# ==============================================================================

class WebhookEndpointCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    target_url: str = Field(..., alias="targetUrl")
    secret_token: Optional[str] = Field(None, alias="secretToken")
    is_active: bool = Field(False, alias="isActive")
    events: List[str] = Field(default_factory=lambda: ["*"])
    timeout_seconds: int = Field(10, ge=1, le=30, alias="timeoutSeconds")


class WebhookEndpointUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    target_url: Optional[str] = Field(None, alias="targetUrl")
    secret_token: Optional[str] = Field(None, alias="secretToken")
    is_active: Optional[bool] = Field(None, alias="isActive")
    events: Optional[List[str]] = None
    timeout_seconds: Optional[int] = Field(None, ge=1, le=30, alias="timeoutSeconds")


class WebhookEndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    name: str
    target_url: str = Field(..., serialization_alias="targetUrl")
    is_active: bool = Field(..., serialization_alias="isActive")
    events: List[str]
    timeout_seconds: int = Field(..., serialization_alias="timeoutSeconds")
    created_at: str = Field(..., serialization_alias="createdAt")
    updated_at: str = Field(..., serialization_alias="updatedAt")


class WebhookDeliveryAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    delivery_id: str = Field(..., serialization_alias="deliveryId")
    event_type: str = Field(..., serialization_alias="eventType")
    payload: Dict[str, Any]
    signature_header: str = Field(..., serialization_alias="signatureHeader")
    response_status_code: Optional[int] = Field(None, serialization_alias="responseStatusCode")
    status: str
    error_message: Optional[str] = Field(None, serialization_alias="errorMessage")
    duration_ms: float = Field(..., serialization_alias="durationMs")
    created_at: str = Field(..., serialization_alias="createdAt")


# ==============================================================================
# Incident Communication & Assignment Schemas
# ==============================================================================

class IncidentCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    comment_type: Literal["comment", "internal_note", "status_change", "escalation", "resolution_summary"] = Field(
        "comment", alias="commentType"
    )


class IncidentCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    incident_id: str = Field(..., serialization_alias="incidentId")
    author_name: str = Field(..., serialization_alias="authorName")
    author_role: str = Field(..., serialization_alias="authorRole")
    comment_type: str = Field(..., serialization_alias="commentType")
    content: str
    created_at: str = Field(..., serialization_alias="createdAt")


class IncidentAssignmentRequest(BaseModel):
    assigned_to_user_id: Optional[str] = Field(None, alias="assignedToUserId")
    assigned_to_name: str = Field(..., alias="assignedToName")


class IncidentAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    incident_id: str = Field(..., serialization_alias="incidentId")
    assigned_to_name: str = Field(..., serialization_alias="assignedToName")
    assigned_by_name: str = Field(..., serialization_alias="assignedByName")
    assigned_at: str = Field(..., serialization_alias="assignedAt")
    is_active: bool = Field(..., serialization_alias="isActive")


class IncidentAcknowledgeRequest(BaseModel):
    note: Optional[str] = "Incident acknowledged by on-call operator."


class IncidentEscalateRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)
    target_level: Optional[int] = Field(None, alias="targetLevel")


# ==============================================================================
# Escalation Policy Schemas
# ==============================================================================

class EscalationLevelRule(BaseModel):
    level: int = Field(..., ge=1, le=5)
    timeout_minutes: int = Field(15, ge=1, le=120, alias="timeoutMinutes")
    channel_ids: List[str] = Field(default_factory=list, alias="channelIds")
    target_roles: List[str] = Field(default_factory=list, alias="targetRoles")


class EscalationPolicyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    severity: Literal["critical", "high", "medium", "low"] = "critical"
    unacknowledged_timeout_minutes: int = Field(15, ge=1, le=120, alias="unacknowledgedTimeoutMinutes")
    max_escalation_level: int = Field(3, ge=1, le=5, alias="maxEscalationLevel")
    rules: List[EscalationLevelRule] = Field(default_factory=list)
    quiet_hours_enabled: bool = Field(False, alias="quietHoursEnabled")
    quiet_hours_start_utc: Optional[str] = Field(None, alias="quietHoursStartUtc")
    quiet_hours_end_utc: Optional[str] = Field(None, alias="quietHoursEndUtc")
    is_active: bool = Field(True, alias="isActive")


class EscalationPolicyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=150)
    severity: Optional[str] = None
    unacknowledged_timeout_minutes: Optional[int] = Field(None, ge=1, le=120, alias="unacknowledgedTimeoutMinutes")
    max_escalation_level: Optional[int] = Field(None, ge=1, le=5, alias="maxEscalationLevel")
    rules: Optional[List[EscalationLevelRule]] = None
    quiet_hours_enabled: Optional[bool] = Field(None, alias="quietHoursEnabled")
    quiet_hours_start_utc: Optional[str] = Field(None, alias="quietHoursStartUtc")
    quiet_hours_end_utc: Optional[str] = Field(None, alias="quietHoursEndUtc")
    is_active: Optional[bool] = Field(None, alias="isActive")


class EscalationPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    name: str
    severity: str
    unacknowledged_timeout_minutes: int = Field(..., serialization_alias="unacknowledgedTimeoutMinutes")
    max_escalation_level: int = Field(..., serialization_alias="maxEscalationLevel")
    rules: List[EscalationLevelRule]
    quiet_hours_enabled: bool = Field(..., serialization_alias="quietHoursEnabled")
    quiet_hours_start_utc: Optional[str] = Field(None, serialization_alias="quietHoursStartUtc")
    quiet_hours_end_utc: Optional[str] = Field(None, serialization_alias="quietHoursEndUtc")
    is_active: bool = Field(..., serialization_alias="isActive")
    created_at: str = Field(..., serialization_alias="createdAt")


class EscalationEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    policy_id: str = Field(..., serialization_alias="policyId")
    incident_id: str = Field(..., serialization_alias="incidentId")
    escalation_level: int = Field(..., serialization_alias="escalationLevel")
    trigger_reason: str = Field(..., serialization_alias="triggerReason")
    action_taken: str = Field(..., serialization_alias="actionTaken")
    notified_channels: List[str] = Field(default_factory=list, serialization_alias="notifiedChannels")
    escalated_at: str = Field(..., serialization_alias="escalatedAt")


# ==============================================================================
# Canary Release & Deployment Intelligence Schemas
# ==============================================================================

class CanaryEvaluationRequest(BaseModel):
    service_id: str = Field(..., alias="serviceId")
    release_tag: str = Field(..., alias="releaseTag")
    traffic_percentage: int = Field(10, ge=1, le=100, alias="trafficPercentage")
    observation_window_minutes: int = Field(30, ge=5, le=180, alias="observationWindowMinutes")
    thresholds: Optional[Dict[str, float]] = None


class ReleaseEvaluationMetricResponse(BaseModel):
    metric_name: str = Field(..., serialization_alias="metricName")
    baseline_value: float = Field(..., serialization_alias="baselineValue")
    canary_value: float = Field(..., serialization_alias="canaryValue")
    delta: float
    threshold_value: float = Field(..., serialization_alias="thresholdValue")
    status: Literal["pass", "warning", "breach"]
    evaluated_at: str = Field(..., serialization_alias="evaluatedAt")


class ReleaseEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    organization_id: str = Field(..., serialization_alias="organizationId")
    service_id: str = Field(..., serialization_alias="serviceId")
    service_name: str = Field(..., serialization_alias="serviceName")
    release_tag: str = Field(..., serialization_alias="releaseTag")
    stage: str
    status: str
    traffic_percentage: int = Field(..., serialization_alias="trafficPercentage")
    observation_window_minutes: int = Field(..., serialization_alias="observationWindowMinutes")
    sample_count: int = Field(..., serialization_alias="sampleCount")
    regression_detected: bool = Field(..., serialization_alias="regressionDetected")
    recommendation: Literal["proceed", "pause", "rollback_recommended"]
    explanation: str
    metrics: List[ReleaseEvaluationMetricResponse] = Field(default_factory=list)
    evaluated_at: str = Field(..., serialization_alias="evaluatedAt")
    created_at: str = Field(..., serialization_alias="createdAt")


# ==============================================================================
# Unified Operations Timeline Schemas
# ==============================================================================

class TimelineItemResponse(BaseModel):
    id: str
    category: Literal["deployment", "alert", "incident", "ai_diagnosis", "recovery", "notification", "escalation"]
    title: str
    detail: str
    service_name: Optional[str] = Field(None, serialization_alias="serviceName")
    severity: Optional[str] = None
    status: Optional[str] = None
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UnifiedTimelineResponse(BaseModel):
    total_events: int = Field(..., serialization_alias="totalEvents")
    items: List[TimelineItemResponse]
