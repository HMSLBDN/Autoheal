# AutoHeal DevOps — Predictive Incident Detection

## Objective
Anticipate resource exhaustion, latency degradation, and service failure conditions before hard alerting thresholds are breached.

## Predictive Horizons
Predictions are computed across three standard operational time horizons:
- **15 Minutes**: Immediate tactical horizon for transient load acceleration and thread pool bottlenecks.
- **30 Minutes**: Medium tactical horizon for memory leak detection, heap exhaustion, and autoscaling pre-warming.
- **60 Minutes**: Strategic horizon for persistent disk capacity growth and diurnal traffic ramps.

## Forecasting Algorithm
1. **Trend Slope Extrapolation**:
   Given a series of sample points $(x_0, y_0), \dots, (x_n, y_n)$, the slope $m$ and variance $R^2$ are computed via ordinary least squares:
   $$m = \frac{\sum (x_i - \bar{x})(y_i - \bar{y})}{\sum (x_i - \bar{x})^2}$$
2. **Rate Conversion**:
   Slope per unit sample is normalized to change per minute based on sampling frequency:
   $$\Delta_{min} = \frac{m}{\Delta t_{sample}}$$
3. **EWMA Baseline Smoothing**:
   $$EWMA_t = \alpha \cdot x_t + (1 - \alpha) \cdot EWMA_{t-1}$$
4. **Target Projection**:
   $$y_{target}(H) = y_{current} + (\Delta_{min} \cdot H)$$
5. **Anomaly Probability**:
   Anomaly probability is weighted by proximity to threshold and trend confidence:
   $$P(\text{anomaly}) = \min\left(0.99, 0.70 + 0.25 \cdot R^2\right) \quad \text{if } y_{target} \ge \text{Threshold}$$

## Noise Suppression & Guardrails
- **Minimum Data Requirement**: Requires at least 3 historical metric samples. If fewer are present, forecasting gracefully yields an empty forecast without raising errors.
- **Realistic Bounds**: Percentage metrics (`cpu_percent`, `memory_percent`, `disk_percent`, `error_rate`) are strictly clamped between 0.0% and 100.0%.
