"""
AutoHeal DevOps — Phase 12 AI Evaluation & Benchmark Test Suite
Validates independent benchmark evaluation on 100 labeled scenarios,
confusion matrix calculations, precision, recall, F1, FPR, FNR,
and strict labeling of synthetic evaluation vs real production observations.
"""

import pytest
from app.services.ai.benchmark_dataset import (
    get_benchmark_dataset,
    run_benchmark_suite,
    Phase12DiagnosticEngine,
)


def test_01_benchmark_dataset_integrity_and_segregation():
    """Validates that development and evaluation datasets have zero data leakage."""
    dev_set, eval_set = get_benchmark_dataset()

    assert len(dev_set) >= 30, f"Expected at least 30 dev scenarios, got {len(dev_set)}"
    assert len(eval_set) >= 100, f"Expected at least 100 eval scenarios, got {len(eval_set)}"

    dev_ids = {s.id for s in dev_set}
    eval_ids = {s.id for s in eval_set}

    # Strict disjointness - zero ID overlap
    overlap = dev_ids.intersection(eval_ids)
    assert len(overlap) == 0, f"Data leakage detected! Overlapping IDs: {overlap}"

    # Strict split tags
    for s in dev_set:
        assert s.split == "dev"
    for s in eval_set:
        assert s.split == "eval"


def test_02_scenario_category_coverage():
    """Ensures comprehensive coverage across all required scenario categories."""
    _, eval_set = get_benchmark_dataset()

    categories = {s.category for s in eval_set}
    required_categories = {
        "normal",
        "noise",
        "insufficient_data",
        "false_positive",
        "memory_leak",
        "thread_starvation",
        "db_starvation",
        "network_partition",
        "disk_pressure",
        "cert_expired",
        "security_drift",
        "duplicate_alert",
    }

    missing = required_categories - categories
    assert len(missing) == 0, f"Missing required evaluation categories: {missing}"

    # Verify counts
    normal_count = sum(1 for s in eval_set if s.category == "normal")
    noise_count = sum(1 for s in eval_set if s.category == "noise")
    insuf_count = sum(1 for s in eval_set if s.category == "insufficient_data")
    fp_count = sum(1 for s in eval_set if s.category == "false_positive")
    real_incidents = sum(1 for s in eval_set if s.is_anomaly)

    assert normal_count == 20
    assert noise_count == 10
    assert insuf_count == 10
    assert fp_count == 10
    assert real_incidents == 50  # 50 real anomaly incidents + 50 non-anomaly/noise/insufficient


def test_03_eval_confusion_matrix_and_statistical_metrics():
    """Executes the 100-scenario evaluation suite and calculates exact statistical metrics."""
    _, eval_set = get_benchmark_dataset()
    results = run_benchmark_suite(eval_set)

    cm = results["confusion_matrix"]
    metrics = results["metrics"]

    assert results["sample_count"] == 100
    assert results["is_synthetic_benchmark"] is True

    # Confusion matrix checks: TP, FP, TN, FN must sum to 100
    total_cm = cm["true_positives"] + cm["false_positives"] + cm["true_negatives"] + cm["false_negatives"]
    assert total_cm == 100

    # Ensure precision, recall, and F1 are high
    assert metrics["precision"] >= 0.90, f"Precision below threshold: {metrics['precision']}"
    assert metrics["recall"] >= 0.90, f"Recall below threshold: {metrics['recall']}"
    assert metrics["f1_score"] >= 0.90, f"F1 score below threshold: {metrics['f1_score']}"

    # False Positive Rate (FPR) and False Negative Rate (FNR) must be low
    assert metrics["false_positive_rate"] <= 0.10, f"FPR exceeded threshold: {metrics['false_positive_rate']}"
    assert metrics["false_negative_rate"] <= 0.10, f"FNR exceeded threshold: {metrics['false_negative_rate']}"

    # Root cause classification accuracy
    assert metrics["root_cause_accuracy"] >= 0.90
    assert metrics["action_recommendation_accuracy"] >= 0.90

    # Mean inference latency must be sub-millisecond for deterministic engine
    assert results["mean_latency_ms"] < 5.0


def test_04_action_allowlist_enforcement():
    """Ensures all recommended actions strictly exist in the system action allowlist."""
    _, eval_set = get_benchmark_dataset()

    for s in eval_set:
        pred = Phase12DiagnosticEngine.evaluate_scenario(s)
        action = pred["predicted_action"]
        assert action in Phase12DiagnosticEngine.ALLOWLISTED_ACTIONS, (
            f"Unallowlisted action returned: {action} for scenario {s.id}"
        )
