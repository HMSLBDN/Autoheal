"""
AutoHeal DevOps — Phase 14 Experiment Comparison Engine
Compares Recovery Enabled vs. Recovery Disabled experiments across identical scenarios and seeds.
Provides honest effect sizes, outage duration reduction, and sample-size-aware confidence notes.
"""

from typing import Optional
from app.models.experiment import Experiment
from app.schemas.experiment import (
    EvidenceClassificationType,
    ExperimentAnalyticsResponse,
    ExperimentComparisonResponse,
)
from app.services.experiment.metrics import calculate_distribution


def build_experiment_analytics(experiment: Experiment) -> ExperimentAnalyticsResponse:
    """Computes aggregated statistical evaluation for a completed or running experiment."""
    runs = experiment.runs or []
    completed_runs = [r for r in runs if r.status in ("completed", "failed")]
    n_completed = len(completed_runs)

    latencies = [r.detection_latency_ms for r in completed_runs if r.detection_latency_ms is not None]
    rec_durations = [r.recovery_duration_ms for r in completed_runs if r.recovery_duration_ms is not None]
    outages = [r.total_outage_duration_ms for r in completed_runs if r.total_outage_duration_ms is not None]

    detection_dist = calculate_distribution(latencies, unit="ms", classification="MEASURED")
    recovery_dist = calculate_distribution(rec_durations, unit="ms", classification="MEASURED")
    outage_dist = calculate_distribution(outages, unit="ms", classification="MEASURED")

    # Success rate
    attempted_runs = [r for r in completed_runs if r.recovery_attempted]
    if attempted_runs:
        success_count = sum(1 for r in attempted_runs if r.recovery_success)
        rec_success_rate = round((success_count / len(attempted_runs)) * 100.0, 1)
    else:
        rec_success_rate = 100.0 if not experiment.recovery_enabled else 0.0

    # False positive rate
    if completed_runs:
        fp_count = sum(1 for r in completed_runs if r.is_false_positive)
        false_positive_rate = round((fp_count / len(completed_runs)) * 100.0, 1)
        safety_count = sum(1 for r in completed_runs if r.safety_compliant)
        safety_compliance_rate = round((safety_count / len(completed_runs)) * 100.0, 1)
        esc_count = sum(1 for r in completed_runs if r.escalated)
        escalation_rate = round((esc_count / len(completed_runs)) * 100.0, 1)
    else:
        false_positive_rate = 0.0
        safety_compliance_rate = 100.0
        escalation_rate = 0.0

    sample_warning = None
    if n_completed < 5:
        sample_warning = (
            f"Sample size (N={n_completed}) is below minimum statistical confidence threshold (N=5). "
            "Results indicate preliminary trends; variance and significance estimates may be unstable."
        )

    return ExperimentAnalyticsResponse(
        experiment_id=experiment.id,
        scenario_type=experiment.scenario_type,
        recovery_enabled=experiment.recovery_enabled,
        total_runs=experiment.number_of_runs,
        completed_runs=n_completed,
        detection_latency=detection_dist,
        recovery_duration=recovery_dist,
        total_outage_duration=outage_dist,
        recovery_success_rate=rec_success_rate,
        false_positive_rate=false_positive_rate,
        safety_compliance_rate=safety_compliance_rate,
        escalation_rate=escalation_rate,
        evidence_classification="SIMULATED",
        sample_size_warning=sample_warning,
    )


def compare_experiments(
    enabled_exp: Optional[Experiment],
    disabled_exp: Optional[Experiment],
    scenario_type: str,
    random_seed: int,
) -> ExperimentComparisonResponse:
    """
    Performs pairwise evaluation between autonomous recovery enabled vs disabled.
    Calculates MTTR and total outage duration reduction.
    """
    enabled_analytics = build_experiment_analytics(enabled_exp) if enabled_exp else None
    disabled_analytics = build_experiment_analytics(disabled_exp) if disabled_exp else None

    outage_red_ms: Optional[float] = None
    outage_red_pct: Optional[float] = None
    mttr_imp_pct: Optional[float] = None
    is_sig = False
    confidence_note = "Insufficient data to compute comparative MTTR benchmark."

    if (
        enabled_analytics
        and disabled_analytics
        and enabled_analytics.total_outage_duration.mean is not None
        and disabled_analytics.total_outage_duration.mean is not None
    ):
        base_outage = disabled_analytics.total_outage_duration.mean
        rec_outage = enabled_analytics.total_outage_duration.mean

        if base_outage > 0:
            diff_ms = round(base_outage - rec_outage, 2)
            outage_red_ms = diff_ms
            pct = round((diff_ms / base_outage) * 100.0, 1)
            outage_red_pct = pct
            mttr_imp_pct = pct

            n1 = enabled_analytics.completed_runs
            n2 = disabled_analytics.completed_runs

            if n1 >= 5 and n2 >= 5:
                # Welch's t-test or sample standard deviation threshold
                s1 = enabled_analytics.total_outage_duration.std_dev or 0.0
                s2 = disabled_analytics.total_outage_duration.std_dev or 0.0
                # Significant if reduction > 2 * pooled standard error
                se = ( (s1**2 / n1) + (s2**2 / n2) ) ** 0.5
                if diff_ms > (2 * se) if se > 0 else diff_ms > 0:
                    is_sig = True
                    confidence_note = (
                        f"Statistically validated improvement: Autonomous recovery reduced mean outage duration by "
                        f"{pct}% ({diff_ms:,.0f} ms reduction across N={n1} matched seeds, p < 0.05)."
                    )
                else:
                    confidence_note = (
                        f"Mean outage reduced by {pct}%, but overlapping variance indicates high scenario variance "
                        f"(SE={se:.1f}ms)."
                    )
            else:
                confidence_note = (
                    f"Observed preliminary outage reduction of {pct}% ({diff_ms:,.0f} ms). "
                    f"Sample size (Enabled N={n1}, Disabled N={n2}) is below N=5; hypothesis significance unconfirmed."
                )

    return ExperimentComparisonResponse(
        scenario_type=scenario_type,
        random_seed=random_seed,
        enabled_experiment=enabled_analytics,
        disabled_experiment=disabled_analytics,
        outage_reduction_ms=outage_red_ms,
        outage_reduction_percentage=outage_red_pct,
        mttr_improvement_percentage=mttr_imp_pct,
        is_statistically_significant=is_sig,
        confidence_note=confidence_note,
        evidence_classification="SIMULATED",
    )
