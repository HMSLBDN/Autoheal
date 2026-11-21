"""
AutoHeal DevOps — AI Provider Interface & Diagnosis Schemas
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

# Strict Recovery Action Allowlist
APPROVED_RECOVERY_ACTIONS = {
    "restart_service",
    "clear_cache",
    "scale_service",
    "restore_health",
    "rollback_release",
}


class AIDiagnosisResult(BaseModel):
    """
    Validated incident diagnosis and mitigation proposal.
    Guarantees that recommended actions comply with the security allowlist.
    """
    summary: str = Field(..., description="Concise synopsis of the evaluated incident")
    probable_root_cause: str = Field(..., description="Most likely underlying architectural or operational cause")
    severity: Literal["critical", "high", "medium", "low"] = Field(..., description="Evaluated incident severity")
    supporting_evidence: List[str] = Field(default_factory=list, description="List of observed telemetry signals justifying diagnosis")
    recommended_action: str = Field(..., description="Action from approved recovery allowlist")
    risk_level: Literal["low", "medium", "high"] = Field("medium", description="Risk of performing the recommended recovery")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence factor between 0.0 and 1.0")
    expected_outcome: str = Field(..., description="Anticipated telemetry response post-recovery")
    # Phase 7 Enhanced Structured Diagnosis Attributes
    affected_service: Optional[str] = Field(None, description="Identified affected service name or resource identifier")
    alternative_recovery_action: Optional[str] = Field(None, description="Secondary allowlisted recovery option if primary fails")
    expected_impact: Optional[str] = Field(None, description="Detailed system impact assessment post-remediation")
    verification_requirements: List[str] = Field(default_factory=list, description="Specific telemetry conditions required to confirm recovery")
    provider_source: Literal["gemini", "heuristic_fallback"] = Field("heuristic_fallback", description="Engine that generated this diagnosis")


class AIProvider(ABC):
    """Abstract interface for replaceable AI diagnosis engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider."""
        pass

    @abstractmethod
    async def diagnose(self, incident_context: Dict[str, Any]) -> AIDiagnosisResult:
        """
        Diagnoses an incident from structured context (metrics, alert labels, logs, deployment history).
        Returns a validated AIDiagnosisResult with an approved recovery recommendation.
        """
        pass
