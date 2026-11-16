"""
AutoHeal DevOps — Alertmanager Webhook Ingestion Schemas
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class AlertLabels(BaseModel):
    alertname: str = Field(..., description="Alert identifier from Prometheus rules")
    service: Optional[str] = Field(None, description="Affected microservice name")
    severity: Optional[str] = Field("high", description="Raw alert severity from Alertmanager")
    environment: Optional[str] = Field("production", description="Runtime environment")
    instance: Optional[str] = None
    job: Optional[str] = None


class AlertAnnotations(BaseModel):
    summary: Optional[str] = Field(None, description="Brief alert title or summary")
    description: Optional[str] = Field(None, description="Detailed threshold description")
    probable_cause: Optional[str] = Field(None, description="Optional diagnostic hint")
    recommended_action: Optional[str] = Field(None, description="Optional suggested action")


class AlertItem(BaseModel):
    status: str = Field(..., description="Alert state: firing or resolved")
    labels: AlertLabels
    annotations: AlertAnnotations = Field(default_factory=AlertAnnotations)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = None


class AlertmanagerWebhookPayload(BaseModel):
    version: Optional[str] = "4"
    groupKey: Optional[str] = None
    status: str = Field(..., description="Group alert status: firing or resolved")
    receiver: Optional[str] = None
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str] = Field(default_factory=dict)
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: Optional[str] = None
    alerts: List[AlertItem] = Field(default_factory=list)


class AlertWebhookResponse(BaseModel):
    status: str = "success"
    processed_alerts: int
    incidents_created: int
    incidents_updated: int
    details: List[str] = Field(default_factory=list)
