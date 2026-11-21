# AutoHeal DevOps — Service Health Risk Scoring

## Overview
AutoHeal computes an explainable composite health risk score ranging from **0.0 to 100.0** for every monitored service.

Rather than presenting an uninterpretable probability, every point added to the risk score is documented as an itemized, auditable `RiskFactor`.

## Mathematical Formulation
The risk score $S$ is computed from a baseline with additive penalties:

$$S = \min\left(100.0, \max\left(0.0, 10.0 + \sum W_i\right)\right)$$

### Itemized Penalties ($W_i$)
1. **Baseline Operating Risk**: $+10.0$ pts (nominal microservice operating risk baseline).
2. **HTTP Error Rate**: $\min(30.0, \text{error\_rate} \times 10.0)$ pts.
3. **P95 Latency Penalty**: If latency $> 100\text{ms}$, $\min(20.0, \frac{\text{latency}}{500.0} \times 20.0)$ pts.
4. **CPU Strain**: $+10.0$ pts if CPU $\ge 80\%$ or trend is `spiking`; $+5.0$ pts if $\ge 65\%$.
5. **Memory Saturation / Leak**: $+15.0$ pts if Memory $\ge 85\%$ or trend is `leaking`; $+7.0$ pts if $\ge 75\%$.
6. **Availability / SLA Penalty**: If availability $< 99.9\%$, $\min(20.0, (99.9 - \text{availability}) \times 10.0)$ pts.
7. **Failed Automated Recoveries**: $+10.0$ pts per recent failed recovery (capped at $+20.0$ pts).
8. **Recent Deployment Regression**: $+10.0$ pts if a release was deployed within 2 hours and error rate increased.
9. **Incident Flapping Frequency**: If $\ge 3$ incidents in 7 days, $\min(10.0, (N - 2) \times 2.5)$ pts.

## Risk Categories
| Risk Range | Category | Color Indicator | Recommended SRE Action |
|---|---|---|---|
| 0 – 30 | Low | Green (`#34D399`) | Nominal operating conditions. Continue passive monitoring. |
| 31 – 60 | Moderate | Yellow (`#FBBF24`) | Moderate strain. Review upcoming traffic demands. |
| 61 – 85 | High | Orange (`#FB923C`) | Elevated failure probability. Review preventive recommendations. |
| 86 – 100 | Critical | Red (`#F87171`) | Imminent failure risk. Operator intervention strongly advised. |
