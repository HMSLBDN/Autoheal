# AutoHeal DevOps — AI Model Evaluation Report

## Benchmark Summary
Evaluated via `scripts/evaluate_models.py` on labeled synthetic corpora.

| Model / Engine | Task Type | Sample Count | Precision | Recall | F1 Score | FPR | MAE | Mean Latency | Synthetic? |
|---|---|---|---|---|---|---|---|---|---|
| **AnomalyDetector-ZScore-EWMA** | Metric Anomaly Detection | 100 | **100.0%** | **100.0%** | **1.0000** | 0.0% | 1.25 | 0.006 ms | **Yes (Labeled Test Corpus)** |
| **HorizonForecaster-Linear-EWMA** | Time-Series Metric Horizon (15m) | 56 | **100.0%** | **100.0%** | **1.0000** | 0.0% | 5.71 | 0.009 ms | **Yes (Labeled Test Corpus)** |
| **DeterministicHeuristic-SRE** | Incident Diagnosis & Remediation | 60 | **75.0%** | **100.0%** | **0.8571** | 25.0% | — | 0.003 ms | **Yes (Synthetic Scenarios)** |

## Metric Definitions
- **Precision**: $\frac{\text{TP}}{\text{TP} + \text{FP}}$
- **Recall**: $\frac{\text{TP}}{\text{TP} + \text{FN}}$
- **F1 Score**: $2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}$
- **False Positive Rate (FPR)**: $\frac{\text{FP}}{\text{FP} + \text{TN}}$
- **False Negative Rate (FNR)**: $\frac{\text{FN}}{\text{FN} + \text{TP}}$
- **Mean Absolute Error (MAE)**: $\frac{1}{N} \sum |y_i - \hat{y}_i|$

## Evaluation Notes
1. **Mathematical Accuracy**: Operator rejections of recommendations are reported separately and do not distort anomaly detection FPR calculations.
2. **Transparency Mandate**: All rows in the evaluation database table `model_evaluation_records` are permanently stamped with `is_synthetic = True` when derived from synthetic benchmarking harnesses.
