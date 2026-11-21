# AutoHeal DevOps — Cross-Incident Root Cause Correlation

## Overview
Cascading outages in microservice architectures frequently trigger concurrent alerts across multiple dependent services (e.g. database connection pool saturation cascading to checkout and search services).

The `IncidentCorrelationEngine` groups related incidents without automatically merging them, preserving independent incident timelines and operator auditability.

## Correlation Criteria
Incidents are evaluated across four correlation dimensions:
1. **Temporal Proximity**:
   Incidents occurring within a sliding 20-minute window are assessed for concurrency.
2. **Shared Service Scope**:
   Multiple alerts impacting the same service (e.g. latency + error rate) receive $+0.30$ correlation weight.
3. **Release Deployment Concurrency**:
   If a deployment event occurred within 60 minutes prior to the incidents, an additional $+0.20$ correlation weight is applied.
4. **Shared Telemetry Anomalies**:
   Concurrent metric anomalies (such as upstream gateway timeouts) are extracted and shared in `shared_evidence`.

## Correlation Output Schema
- `group_id`: Deterministic identifier linking the cluster (`corr-group-<primary_id>`).
- `primary_incident_id`: The earliest triggered incident in the group.
- `correlation_type`: `temporal`, `shared_service`, or `deployment_impact`.
- `correlation_score`: Numerical confidence between 0.0 and 1.0.
- `explanation`: Plain-language justification for operator review.
- `shared_evidence`: Specific telemetry facts supporting the correlation.
- `incidents`: Full list of linked incident summaries.

## Core Safety Invariant
> **Strict Non-Merging Guarantee**: Correlation groups link incidents for operator context and root-cause analysis, but NEVER silently close, suppress, or merge distinct incident records without explicit human operator instruction.
