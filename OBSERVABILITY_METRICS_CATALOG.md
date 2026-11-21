# AutoHeal DevOps — Enterprise Observability Metrics Catalog

## 1. Overview

AutoHeal DevOps SaaS Phase 10 provides comprehensive real-time telemetry compliant with the **OpenMetrics** and **Prometheus 2.0+** format. Telemetry is available via:
- Prometheus Scrape Endpoint: `GET /api/v1/observability/metrics`
- JSON Observability Statistics: `GET /api/v1/observability/stats`

---

## 2. Metrics Catalog

### 2.1 HTTP & API Gateway Metrics

| Metric Name | Type | Labels / Dimensions | Description | Alerting Baseline |
|:---|:---|:---|:---|:---|
| `autoheal_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total count of HTTP requests processed by API Gateway | Spike > 300% in 5m |
| `autoheal_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request execution latency distribution | p99 > 1.5s for 5m |
| `autoheal_http_requests_in_flight` | Gauge | `service` | Current number of active concurrently running requests | > 200 concurrent |

### 2.2 Incident & Self-Healing Pipeline Metrics

| Metric Name | Type | Labels / Dimensions | Description | Alerting Baseline |
|:---|:---|:---|:---|:---|
| `autoheal_incidents_active` | Gauge | `severity`, `organization_id` | Number of currently unresolved incidents | Critical > 0 for > 15m |
| `autoheal_remediations_total` | Counter | `action_type`, `status` | Total automated/operator remediations executed | Failure rate > 10% |
| `autoheal_remediation_duration_seconds` | Histogram | `action_type` | Duration from trigger to health recovery verification | > 300s (MTTR SLA breach) |
| `autoheal_ai_diagnoses_total` | Counter | `model`, `confidence_bracket` | Total AI incident diagnoses generated | Confidence < 0.6 > 25% |

### 2.3 Identity, SSO & Session Metrics

| Metric Name | Type | Labels / Dimensions | Description | Alerting Baseline |
|:---|:---|:---|:---|:---|
| `autoheal_sso_authentications_total` | Counter | `provider_type`, `status` | Identity provider sign-in attempts | Failure rate > 5% |
| `autoheal_active_sessions_total` | Gauge | `organization_id` | Count of active unexpired user sessions | Anomaly > 500% |
| `autoheal_security_events_total` | Counter | `category`, `severity` | Emitted security audit log events | Critical severity > 0 |

### 2.4 Infrastructure Agent & mTLS Security Metrics

| Metric Name | Type | Labels / Dimensions | Description | Alerting Baseline |
|:---|:---|:---|:---|:---|
| `autoheal_agent_mtls_handshakes_total` | Counter | `organization_id`, `result` | Mutual TLS client handshake negotiations | Result == "failed" > 3/m |
| `autoheal_agent_certs_active` | Gauge | `organization_id` | Count of valid unrevoked agent client certificates | Drop > 20% in 10m |
| `autoheal_agent_certs_expiring_soon` | Gauge | `organization_id`, `window` | Certificates expiring within 14 days | > 0 triggers warning |

### 2.5 Database & Disaster Recovery Metrics

| Metric Name | Type | Labels / Dimensions | Description | Alerting Baseline |
|:---|:---|:---|:---|:---|
| `autoheal_db_connections_active` | Gauge | `pool` | Active database connections in connection pool | > 85% pool capacity |
| `autoheal_db_query_duration_seconds` | Histogram | `operation` | Database transaction execution latency | p95 > 250ms |
| `autoheal_backup_rto_seconds` | Gauge | `target` | Measured Recovery Time Objective during DR tests | > 900s (15 min SLA) |
| `autoheal_backup_rpo_seconds` | Gauge | `target` | Measured Recovery Point Objective during DR tests | > 300s (5 min SLA) |

---

## 3. Prometheus Alerting Rules Integration

Prometheus alerts are packaged in `monitoring/prometheus/alert_rules.yml`. Rules link directly to production runbooks:

- `HighIncidentVolume`: Fires when `sum(rate(autoheal_incidents_active[5m])) > 10`.
- `AgentCertificateExpiring`: Fires when `autoheal_agent_certs_expiring_soon > 0`.
- `MtlsHandshakeFailureSpike`: Fires when failed handshakes exceed 5% of total over 5m.
- `DatabaseConnectionPoolExhaustion`: Fires when `autoheal_db_connections_active / autoheal_db_connections_max > 0.85`.
- `DisasterRecoverySlaBreach`: Fires when `autoheal_backup_rto_seconds > 900` or `autoheal_backup_rpo_seconds > 300`.

---

## 4. Grafana Enterprise Dashboard

The enterprise visualization dashboard is exported in `monitoring/grafana/dashboards/autoheal_enterprise.json`. It provides:
- Live Service Health & Traffic KPIs
- Incident Rate & Automated MTTR Distribution
- Active Identity Sessions & SSO Authentication Flow
- Agent PKI Health (active certs, revoked certs, expiring certs)
- Database Performance & Automated DR SLA Verification gauges
