"""
AutoHeal DevOps — Historical Incident Intelligence & Similarity Engine
Finds previous historical incidents with similar failure characteristics
within the same tenant organization to inform AI and operator decision support.
"""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.recovery import RecoveryAction


def tokenize(text: str) -> Set[str]:
    """Extracts lowercase alpha-numeric tokens of length >= 3."""
    if not text:
        return set()
    words = re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower())
    return set(words)


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """Computes Jaccard index: |A ∩ B| / |A ∪ B|."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


class HistoricalIntelligenceEngine:
    """
    Tenant-isolated similarity matcher linking incoming incidents to historical incidents.
    Extracts previous root causes, verified recovery actions, and resolution times.
    """

    @staticmethod
    def compute_similarity(
        current_service: str,
        current_title: str,
        current_desc: str,
        hist_service: str,
        hist_title: str,
        hist_desc: str,
    ) -> float:
        """
        Calculates weighted similarity score (0.0 to 1.0):
        40% service match, 35% title token overlap, 25% description token overlap.
        """
        service_score = 1.0 if current_service.strip().lower() == hist_service.strip().lower() else 0.0

        title_tokens_cur = tokenize(current_title)
        title_tokens_hist = tokenize(hist_title)
        title_score = jaccard_similarity(title_tokens_cur, title_tokens_hist)

        desc_tokens_cur = tokenize(current_desc)
        desc_tokens_hist = tokenize(hist_desc)
        desc_score = jaccard_similarity(desc_tokens_cur, desc_tokens_hist)

        weighted_score = (0.40 * service_score) + (0.35 * title_score) + (0.25 * desc_score)
        return round(weighted_score, 2)

    async def find_similar_incidents(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        service_name: str,
        incident_title: str,
        incident_description: str = "",
        exclude_incident_id: Optional[str] = None,
        limit: int = 5,
        min_similarity_threshold: float = 0.25,
    ) -> List[Dict[str, Any]]:
        """
        Searches historical incidents belonging ONLY to the tenant organization.
        Finds the top matches exceeding min_similarity_threshold.
        """
        query = select(Incident).where(
            and_(
                Incident.organization_id == organization_id,
            )
        ).order_by(desc(Incident.detected_at)).limit(50)

        result = await db.execute(query)
        historical_incidents = result.scalars().all()

        matches: List[Dict[str, Any]] = []

        for hist in historical_incidents:
            if exclude_incident_id and str(hist.id) == str(exclude_incident_id):
                continue

            score = self.compute_similarity(
                current_service=service_name,
                current_title=incident_title,
                current_desc=incident_description,
                hist_service=hist.service_name or "",
                hist_title=hist.title or "",
                hist_desc=hist.probable_cause or "",
            )

            if score >= min_similarity_threshold:
                # Query recovery action for this historical incident
                rec_query = select(RecoveryAction).where(
                    RecoveryAction.incident_id == hist.id
                ).order_by(desc(RecoveryAction.requested_at))
                rec_res = await db.execute(rec_query)
                rec_action = rec_res.scalars().first()

                action_type = rec_action.action if rec_action else "restart_service"
                rec_outcome = rec_action.status if rec_action else (
                    "resolved" if hist.status == "resolved" else "unknown"
                )

                duration_min: Optional[float] = None
                hist_time = hist.detected_at or getattr(hist, "created_at", None)
                if hist.resolved_at and hist_time:
                    duration_min = round(
                        (hist.resolved_at - hist_time).total_seconds() / 60.0,
                        1,
                    )

                matches.append({
                    "incident_id": hist.id,
                    "title": hist.title,
                    "service_name": hist.service_name or "unknown",
                    "similarity_score": score,
                    "previous_root_cause": hist.probable_cause or "Operational anomaly",
                    "previous_recovery_action": hist.recommended_action or action_type,
                    "recovery_outcome": rec_outcome,
                    "resolution_duration_minutes": duration_min,
                    "detected_at": hist_time.isoformat() if hist_time else "",
                })

        # Sort descending by similarity score
        matches.sort(key=lambda m: m["similarity_score"], reverse=True)
        return matches[:limit]
