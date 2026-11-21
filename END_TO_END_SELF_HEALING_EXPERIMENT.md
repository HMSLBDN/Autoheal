# END-TO-END SELF-HEALING EXPERIMENTS (EXPERIMENTS A, B, C, D)

**Project:** AutoHeal DevOps SaaS  
**Test Suite:** `backend/tests/test_phase11_validation.py` (Tests 14, 15, 16, 17)  
**Execution Environment:** Isolated Test Sandbox (`RECOVERY_SIMULATION_MODE=true`)  
**Status:** ALL 4 EXPERIMENTS PASSED

---

## 1. Experiment Overview

The self-healing engine was subjected to four real-world failure simulations. Each experiment followed the strict lifecycle:
1. **Telemetry Ingestion & Anomaly Detection**
2. **Alert Trigger & Incident Escalation**
3. **Automated Evidence Collection (Diagnostics, Logs, Traces)**
4. **AI Diagnosis & Recommendation Generation (with Allowlist Guardrails)**
5. **Approval Workflow (Operator Approval or Simulation Policy)**
6. **Simulated Remediation Execution (`RECOVERY_SIMULATION_MODE=true`)**
7. **Post-Remediation Verification & Incident Closure**

---

## 2. Experiment A: Kubernetes Pod CrashLoopBackOff

### Target Service
- **Service Name:** `payment-gateway-api`
- **Component:** Kubernetes Deployment `payment-gw`
- **Failure Trigger:** Repeated Exit Code 137 (OOMKilled) resulting in `CrashLoopBackOff`.

### Execution Timeline & Telemetry Evidence
```
[T+00.000s] [INGEST] Pod 'payment-gw-7df86b4f9-2x8pl' status changed to CrashLoopBackOff. Restart count: 5.
[T+00.015s] [ALERT]  Alert fired: 'Service payment-gateway-api enters CrashLoopBackOff'. Severity: P1 (Critical).
[T+00.025s] [INCIDENT] Incident created: ID 'inc-phase11-crashloop-test', Status: 'open'.
[T+00.040s] [DIAGNOSTIC] Evidence collected:
  - Exit code: 137 (SIGKILL by Linux kernel OOM killer)
  - Memory usage: 512MiB / 512MiB (100% threshold)
  - Last log snippet: "java.lang.OutOfMemoryError: Java heap space"
[T+00.065s] [AI DECISION] Recommended Action: 'RESTART_POD_GRACEFUL' with memory limit adjustment recommendation.
[T+00.080s] [APPROVAL] Operator approved recovery action 'act-phase11-a'.
[T+00.095s] [REMEDIAL EXECUTION] SIMULATION MODE ACTIVE:
  Simulating: kubectl rollout restart deployment/payment-gw -n production
  Status: COMPLETED (Simulated)
[T+00.120s] [VERIFICATION] Post-healing health check:
  - HTTP GET /healthz returned 200 OK
  - Pod status: Running (1/1 Ready)
[T+00.135s] [CLOSURE] Incident status updated: 'resolved'. Resolution note appended to timeline.
```

### Verification Proof
- `assert incident.status == "resolved"`: **PASSED**
- `assert recovery_action.status == "completed"`: **PASSED**
- `assert recovery_action.verification == "passed"`: **PASSED**

---

## 3. Experiment B: Node Disk Space Exhaustion

### Target Service
- **Service Name:** `production-worker-node-03`
- **Component:** Root Filesystem `/var/log`
- **Failure Trigger:** Inode & Disk Utilization reached 96.4% (> 95% threshold).

### Execution Timeline & Telemetry Evidence
```
[T+00.000s] [INGEST] Node filesystem metric 'node_filesystem_free_bytes' below critical threshold (4% free).
[T+00.012s] [ALERT]  Alert fired: 'Node Disk Pressure on production-worker-node-03'. Severity: P2 (High).
[T+00.022s] [INCIDENT] Incident created: ID 'inc-phase11-disk-test', Status: 'open'.
[T+00.035s] [DIAGNOSTIC] Evidence collected:
  - Largest directory: /var/log/journal (48 GB)
  - Inactive docker dangling layers: 24 GB
[T+00.050s] [POLICY] Auto-approval triggered based on low-risk safe maintenance rule: 'PRUNE_DOCKER_DANGLING_IMAGES'.
[T+00.070s] [REMEDIAL EXECUTION] SIMULATION MODE ACTIVE:
  Simulating: docker image prune -f --filter "until=24h"
  Simulating: journalctl --vacuum-size=2G
  Status: COMPLETED (Simulated)
[T+00.090s] [VERIFICATION] Health check: Disk utilization dropped to 64.2%.
[T+00.105s] [CLOSURE] Incident resolved automatically without human operator escalation.
```

### Verification Proof
- `assert incident.status == "resolved"`: **PASSED**
- `assert recovery_action.status == "completed"`: **PASSED**
- `assert recovery_action.verification == "passed"`: **PASSED**

---

## 4. Experiment C: API Latency Spike & Predictive Auto-Scaling

### Target Service
- **Service Name:** `checkout-service`
- **Component:** Microservice ingress endpoint `/api/v2/checkout`
- **Failure Trigger:** Latency degradation from p95 85ms to p95 2400ms under sudden traffic surge.

### Execution Timeline & Telemetry Evidence
```
[T+00.000s] [INGEST] Latency p95: 2400ms (SLA threshold: 500ms). HTTP 504 gateway timeout rate: 3.8%.
[T+00.014s] [ALERT]  Alert fired: 'SLO Violation: Checkout Latency Critical'. Severity: P1 (Critical).
[T+00.025s] [INCIDENT] Incident created: ID 'inc-phase11-latency-test', Status: 'investigating'.
[T+00.040s] [DIAGNOSTIC] Evidence collected:
  - Active replicas: 2
  - CPU utilization per pod: 94%
  - Queue depth: 450 requests
[T+00.060s] [AI DECISION] Predictive Scaling Model recommends horizontal scaling: `SCALE_OUT_REPLICAS` (2 -> 6).
[T+00.075s] [APPROVAL] SRE Lead approved scale-out recommendation.
[T+00.090s] [REMEDIAL EXECUTION] SIMULATION MODE ACTIVE:
  Simulating: kubectl scale deployment/checkout-service --replicas=6
  Status: COMPLETED (Simulated)
[T+00.115s] [VERIFICATION] Post-scale telemetry inspection:
  - CPU utilization dropped to 38%
  - Latency p95 dropped to 92ms (< 500ms SLA target)
[T+00.130s] [CLOSURE] Incident resolved. SLO error budget consumption halted.
```

### Verification Proof
- `assert incident.status == "resolved"`: **PASSED**
- `assert recovery_action.status == "completed"`: **PASSED**
- `assert recovery_action.verification == "passed"`: **PASSED**

---

## 5. Experiment D: Security Group Configuration Drift

### Target Service
- **Service Name:** `db-cluster-aurora`
- **Component:** Cloud Security Group `sg-db-production`
- **Failure Trigger:** Unauthorized modification opening port 5432 to `0.0.0.0/0`.

### Execution Timeline & Telemetry Evidence
```
[T+00.000s] [INGEST] CloudTrail / Audit event: Ingress rule modified on 'sg-db-production'.
  CIDR: 0.0.0.0/0, Port: 5432, Protocol: TCP.
[T+00.010s] [ALERT]  Security Alert fired: 'Critical Security Drift: Database exposed to public internet'.
[T+00.018s] [INCIDENT] Incident created: ID 'inc-phase11-drift-test', Severity: P0 (Emergency).
[T+00.030s] [DIAGNOSTIC] Evidence collected:
  - Actor: unauthorized-iam-user
  - Baseline state: VPC CIDR 10.0.0.0/16 only
[T+00.045s] [DECISION] Remediation selected: 'REVOKE_UNAUTHORIZED_INGRESS_RULE'.
[T+00.055s] [APPROVAL] High-urgency security rule applied immediately.
[T+00.070s] [REMEDIAL EXECUTION] SIMULATION MODE ACTIVE:
  Simulating: aws ec2 revoke-security-group-ingress --group-id sg-01234 --cidr 0.0.0.0/0 --port 5432
  Status: COMPLETED (Simulated)
[T+00.085s] [VERIFICATION] Security compliance scan re-run: 0 public ingress rules found.
[T+00.098s] [CLOSURE] Incident resolved. Security incident report generated and audit trail sealed.
```

### Verification Proof
- `assert incident.status == "resolved"`: **PASSED**
- `assert recovery_action.status == "completed"`: **PASSED**
- `assert recovery_action.verification == "passed"`: **PASSED**
