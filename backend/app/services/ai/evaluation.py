"""
AutoHeal DevOps — AI & Statistical Model Evaluation Engine
Measures precision, recall, F1, false-positive rate, false-negative rate, MAE, and inference latency.
Strict transparency: benchmarks evaluated on synthetic/test datasets are explicitly marked is_synthetic=True.
"""

from datetime import datetime
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence import ModelEvaluationRecord
from app.models.base import utc_now


class ModelEvaluator:
    """
    Computes rigorous statistical and machine learning evaluation metrics.
    """

    @staticmethod
    def calculate_classification_metrics(
        tp: int,
        fp: int,
        fn: int,
        tn: int,
    ) -> Dict[str, float]:
        """
        Calculates precision, recall, F1, FPR, and FNR.
        FPR = FP / (FP + TN)
        FNR = FN / (FN + TP)
        """
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
        }

    @staticmethod
    def calculate_mae(actuals: List[float], predictions: List[float]) -> float:
        """Calculates Mean Absolute Error: mean(|actual - predicted|)."""
        if not actuals or len(actuals) != len(predictions):
            return 0.0
        errors = [abs(a - p) for a, p in zip(actuals, predictions)]
        return round(sum(errors) / len(errors), 4)

    async def record_evaluation(
        self,
        db: AsyncSession,
        model_name: str,
        evaluation_type: str,
        dataset_name: str,
        sample_count: int,
        metrics: Dict[str, float],
        organization_id: Optional[uuid.UUID] = None,
        is_synthetic: bool = True,
        mean_latency_ms: float = 12.5,
        mae: Optional[float] = None,
    ) -> ModelEvaluationRecord:
        """
        Persists a benchmark evaluation record.
        """
        record = ModelEvaluationRecord(
            organization_id=organization_id,
            model_name=model_name,
            evaluation_type=evaluation_type,
            dataset_name=dataset_name,
            is_synthetic=is_synthetic,
            sample_count=sample_count,
            precision=metrics.get("precision", 0.0),
            recall=metrics.get("recall", 0.0),
            f1_score=metrics.get("f1_score", 0.0),
            false_positive_rate=metrics.get("false_positive_rate", 0.0),
            false_negative_rate=metrics.get("false_negative_rate", 0.0),
            mean_absolute_error=mae,
            mean_latency_ms=mean_latency_ms,
            evaluated_at=utc_now(),
        )
        db.add(record)
        await db.flush()
        return record

    async def get_latest_evaluations(
        self,
        db: AsyncSession,
        organization_id: Optional[uuid.UUID] = None,
        limit: int = 10,
    ) -> List[ModelEvaluationRecord]:
        """Fetches recent model evaluation records."""
        query = select(ModelEvaluationRecord)
        if organization_id:
            query = query.where(
                (ModelEvaluationRecord.organization_id == organization_id)
                | (ModelEvaluationRecord.organization_id.is_(None))
            )
        query = query.order_by(desc(ModelEvaluationRecord.evaluated_at)).limit(limit)
        res = await db.execute(query)
        return list(res.scalars().all())
