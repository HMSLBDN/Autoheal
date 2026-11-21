"""
AutoHeal DevOps — Phase 14 Experiment Metrics & Statistics Engine
Calculates detection latency, recovery duration, total outage duration,
and rigorous distributions with honest sample size awareness.
"""

import math
from typing import List, Optional, Sequence
from app.schemas.experiment import EvidenceClassificationType, MetricDistribution


def calculate_distribution(
    values: Sequence[float],
    unit: str = "ms",
    classification: EvidenceClassificationType = "MEASURED",
) -> MetricDistribution:
    """
    Computes min, max, mean, median, std_dev, p95 across scalar samples.
    Accurately flags small_sample_size when sample_count < 5.
    """
    valid = [float(v) for v in values if v is not None and not math.isnan(v)]
    n = len(valid)

    if n == 0:
        return MetricDistribution(
            min=None,
            max=None,
            mean=None,
            median=None,
            std_dev=None,
            p95=None,
            sample_count=0,
            small_sample_size=True,
            unit=unit,
            classification=classification,
        )

    valid_sorted = sorted(valid)
    min_val = round(valid_sorted[0], 2)
    max_val = round(valid_sorted[-1], 2)
    mean_val = round(sum(valid_sorted) / n, 2)

    # Median
    if n % 2 == 1:
        median_val = round(valid_sorted[n // 2], 2)
    else:
        median_val = round((valid_sorted[(n // 2) - 1] + valid_sorted[n // 2]) / 2.0, 2)

    # Standard deviation (sample standard deviation with n-1 ddof)
    if n >= 2:
        variance = sum((x - mean_val) ** 2 for x in valid_sorted) / (n - 1)
        std_dev_val = round(math.sqrt(variance), 2)
    else:
        std_dev_val = 0.0

    # P95 percentile
    p95_idx = int(math.ceil(0.95 * n)) - 1
    p95_idx = max(0, min(p95_idx, n - 1))
    p95_val = round(valid_sorted[p95_idx], 2)

    return MetricDistribution(
        min=min_val,
        max=max_val,
        mean=mean_val,
        median=median_val,
        std_dev=std_dev_val,
        p95=p95_val,
        sample_count=n,
        small_sample_size=(n < 5),
        unit=unit,
        classification=classification,
    )
