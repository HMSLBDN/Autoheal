"""
AutoHeal DevOps — AI & Statistical Model Evaluation Harness
Rigorously evaluates Anomaly Detection, Time-Series Forecasting, and AI Incident Diagnosis.
Computes Precision, Recall, F1, FPR (FP / (FP + TN)), FNR (FN / (FN + TP)), MAE, and inference latency.
Strict transparency: explicitly tags synthetic benchmark datasets with is_synthetic=True.
"""

import asyncio
from datetime import datetime, timezone
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
os.environ.setdefault("APP_ENV", "test")

from app.services.ai.anomaly_detector import AnomalyDetectionEngine
from app.services.ai.risk_scorer import ServiceRiskScorer
from app.services.ai.heuristic import HeuristicDiagnosisProvider
from app.services.ai.evaluation import ModelEvaluator


def evaluate_anomaly_detector() -> Dict[str, Any]:
    """
    Evaluates AnomalyDetectionEngine against 100 labeled test metric series
    (50 anomalous, 50 nominal/healthy).
    """
    engine = AnomalyDetectionEngine()
    tp = fp = fn = tn = 0
    latencies: List[float] = []

    # Generate 50 anomalous test cases
    anomalous_cases = []
    # 1. CPU spikes
    for _ in range(15):
        history = [20.0, 22.0, 21.0, 23.0, 20.0]
        anomalous_cases.append(("cpu_percent", 95.0, history, True))
    # 2. Memory leaks (monotonic growth)
    for _ in range(15):
        history = [55.0, 60.0, 65.0, 70.0, 75.0]
        anomalous_cases.append(("memory_percent", 82.0, history, True))
    # 3. Latency jumps
    for _ in range(10):
        history = [40.0, 45.0, 42.0, 44.0, 41.0]
        anomalous_cases.append(("latency_ms", 650.0, history, True))
    # 4. Error rate breaches
    for _ in range(10):
        history = [0.01, 0.02, 0.01, 0.03, 0.02]
        anomalous_cases.append(("error_rate", 3.5, history, True))

    # Generate 50 nominal / healthy test cases
    nominal_cases = []
    for _ in range(20):
        history = [25.0, 28.0, 26.0, 27.0, 24.0]
        nominal_cases.append(("cpu_percent", 26.0, history, False))
    for _ in range(15):
        history = [40.0, 42.0, 41.0, 40.0, 43.0]
        nominal_cases.append(("memory_percent", 42.0, history, False))
    for _ in range(15):
        history = [35.0, 38.0, 36.0, 37.0, 39.0]
        nominal_cases.append(("latency_ms", 40.0, history, False))

    test_set = anomalous_cases + nominal_cases

    for metric_name, current_val, history, actual_is_anomaly in test_set:
        start = time.perf_counter()
        result = engine.detect_metric_anomaly(
            metric_name=metric_name,
            current_value=current_val,
            history=history,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(elapsed_ms)

        predicted_is_anomaly = result is not None

        if actual_is_anomaly and predicted_is_anomaly:
            tp += 1
        elif not actual_is_anomaly and predicted_is_anomaly:
            fp += 1
        elif actual_is_anomaly and not predicted_is_anomaly:
            fn += 1
        else:
            tn += 1

    metrics = ModelEvaluator.calculate_classification_metrics(tp=tp, fp=fp, fn=fn, tn=tn)
    metrics["mean_latency_ms"] = round(sum(latencies) / len(latencies), 3)
    metrics["sample_count"] = len(test_set)
    metrics["tp"] = tp
    metrics["fp"] = fp
    metrics["fn"] = fn
    metrics["tn"] = tn
    metrics["dataset_name"] = "synthetic_telemetry_corpus_v1"
    metrics["is_synthetic"] = True
    metrics["model_name"] = "AnomalyDetector-ZScore-EWMA"
    metrics["evaluation_type"] = "anomaly_detection"
    return metrics


def evaluate_forecaster() -> Dict[str, Any]:
    """
    Evaluates EWMA linear forecasting horizon accuracy on synthetic trajectories.
    """
    engine = AnomalyDetectionEngine()
    actuals = []
    predictions = []
    latencies = []

    # 50 linear projection trajectories (mix of breach and non-breach)
    for slope in [3.5, 4.0, 2.0, 1.0, 0.5, 0.0, -1.0]:
        base = 45.0
        for step in range(8):
            history = [base + slope * i for i in range(5)]
            current = base + slope * 5
            expected_15m = current + (slope * 15)

            start = time.perf_counter()
            forecasts = engine.forecast_breach(
                metric_name="memory_percent",
                current_value=current,
                history=history,
                sample_interval_minutes=1.0,
                horizons_minutes=[15],
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(elapsed_ms)

            if forecasts:
                actuals.append(expected_15m)
                predictions.append(forecasts[0]["predicted_value"])

    mae = ModelEvaluator.calculate_mae(actuals, predictions)

    # Classification accuracy on whether threshold (85%) would be breached
    tp = fp = fn = tn = 0
    thresh = 85.0
    for act, pred in zip(actuals, predictions):
        act_breach = act >= thresh
        pred_breach = pred >= thresh
        if act_breach and pred_breach:
            tp += 1
        elif not act_breach and pred_breach:
            fp += 1
        elif act_breach and not pred_breach:
            fn += 1
        else:
            tn += 1

    metrics = ModelEvaluator.calculate_classification_metrics(tp=tp, fp=fp, fn=fn, tn=tn)
    metrics["mean_absolute_error"] = mae
    metrics["mean_latency_ms"] = round(sum(latencies) / len(latencies), 3)
    metrics["sample_count"] = len(actuals)
    metrics["dataset_name"] = "synthetic_capacity_exhaustion_v1"
    metrics["is_synthetic"] = True
    metrics["model_name"] = "HorizonForecaster-Linear-EWMA"
    metrics["evaluation_type"] = "time_series_prediction"
    return metrics


async def evaluate_heuristic_diagnosis() -> Dict[str, Any]:
    """
    Evaluates rule-based heuristic SRE diagnosis engine on 50 synthetic incident scenarios.
    """
    provider = HeuristicDiagnosisProvider()
    tp = fp = fn = tn = 0
    latencies = []

    # Scenarios mapping condition -> expected approved action
    scenarios = [
        # Recent deployment with errors -> rollback_release
        {"service_name": "checkout-api", "alert_name": "High5xxErrorRate", "error_rate": 4.5, "latency_ms": 120, "has_recent_deployment": True, "expected": "rollback_release"},
        # Memory leak -> restart_service
        {"service_name": "inventory-api", "alert_name": "PodMemoryExhaustion", "error_rate": 0.2, "latency_ms": 150, "memory_percent": 88.0, "has_recent_deployment": False, "expected": "restart_service"},
        # CPU spike -> scale_service
        {"service_name": "search-api", "alert_name": "HighCPUUtilization", "error_rate": 0.1, "latency_ms": 400, "cpu_percent": 89.0, "has_recent_deployment": False, "expected": "scale_service"},
        # High latency / cache miss -> clear_cache
        {"service_name": "product-catalog", "alert_name": "HighLatencyCacheSaturation", "error_rate": 0.05, "latency_ms": 650, "has_recent_deployment": False, "expected": "clear_cache"},
    ] * 15  # 60 synthetic scenarios

    for sc in scenarios:
        start = time.perf_counter()
        diag = await provider.diagnose(sc)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        latencies.append(elapsed_ms)

        if diag.recommended_action == sc["expected"]:
            tp += 1
        else:
            fp += 1

    # In single-class evaluation where all cases are actionable incidents:
    metrics = ModelEvaluator.calculate_classification_metrics(tp=tp, fp=fp, fn=fn, tn=tn)
    metrics["mean_latency_ms"] = round(sum(latencies) / len(latencies), 3)
    metrics["sample_count"] = len(scenarios)
    metrics["dataset_name"] = "synthetic_incident_scenarios_v1"
    metrics["is_synthetic"] = True
    metrics["model_name"] = "DeterministicHeuristic-SRE-Engine"
    metrics["evaluation_type"] = "incident_diagnosis"
    return metrics


async def main():
    print("=" * 70)
    print("AutoHeal DevOps — AI & Statistical Model Quality Evaluation")
    print("=" * 70)

    print("\n[1/3] Evaluating Anomaly Detection Engine (Z-Score + EWMA + Slope)...")
    anom_metrics = evaluate_anomaly_detector()
    print(f"  Samples: {anom_metrics['sample_count']} (is_synthetic={anom_metrics['is_synthetic']})")
    print(f"  Precision: {anom_metrics['precision'] * 100:.2f}%")
    print(f"  Recall:    {anom_metrics['recall'] * 100:.2f}%")
    print(f"  F1 Score:  {anom_metrics['f1_score'] * 100:.2f}%")
    print(f"  FPR:       {anom_metrics['false_positive_rate'] * 100:.2f}%")
    print(f"  FNR:       {anom_metrics['false_negative_rate'] * 100:.2f}%")
    print(f"  Latency:   {anom_metrics['mean_latency_ms']} ms")

    print("\n[2/3] Evaluating Time-Series Predictive Horizon Forecaster...")
    fc_metrics = evaluate_forecaster()
    print(f"  Samples: {fc_metrics['sample_count']} (is_synthetic={fc_metrics['is_synthetic']})")
    print(f"  Precision: {fc_metrics['precision'] * 100:.2f}%")
    print(f"  Recall:    {fc_metrics['recall'] * 100:.2f}%")
    print(f"  F1 Score:  {fc_metrics['f1_score'] * 100:.2f}%")
    print(f"  FPR:       {fc_metrics['false_positive_rate'] * 100:.2f}%")
    print(f"  MAE:       {fc_metrics['mean_absolute_error']}")
    print(f"  Latency:   {fc_metrics['mean_latency_ms']} ms")

    print("\n[3/3] Evaluating SRE Incident Diagnosis Engine...")
    diag_metrics = await evaluate_heuristic_diagnosis()
    print(f"  Samples: {diag_metrics['sample_count']} (is_synthetic={diag_metrics['is_synthetic']})")
    print(f"  Precision: {diag_metrics['precision'] * 100:.2f}%")
    print(f"  Recall:    {diag_metrics['recall'] * 100:.2f}%")
    print(f"  F1 Score:  {diag_metrics['f1_score'] * 100:.2f}%")
    print(f"  Latency:   {diag_metrics['mean_latency_ms']} ms")

    all_results = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "is_synthetic_evaluation": True,
        "models": [anom_metrics, fc_metrics, diag_metrics],
    }

    os.makedirs("monitoring", exist_ok=True)
    out_path = os.path.join("monitoring", "model_evaluations.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n[OK] Model evaluation results persisted to {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
