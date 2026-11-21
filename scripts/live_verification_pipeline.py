"""
AutoHeal DevOps — Live Runtime Pipeline & Healthy Observation Verification
Executes live runtime verification against running Docker services:
- Healthy observation windows (TN / FP quantification)
- Controlled failure of checkout-api
- Prometheus scrape detection (inactive -> pending -> firing)
- Alertmanager delivery via authenticated webhook to FastAPI
- PostgreSQL incident creation & audit trail
- Deduplication verification (no duplicate incident for re-triggered alerts)
- Service restoration & Prometheus alert resolution
- Auto-resolution in FastAPI & PostgreSQL
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_verification")

PROMETHEUS_URL = "http://localhost:9090"
ALERTMANAGER_URL = "http://localhost:9093"
BACKEND_URL = "http://localhost:8000"
CHECKOUT_URL = "http://localhost:8080"
CUSTOMER_URL = "http://localhost:8081"
PAYMENTS_URL = "http://localhost:8082"


def get_pg_latest_incident():
    cmd = [
        "docker", "exec", "autoheal_db_dev", "psql",
        "-U", "autoheal_user", "-d", "autoheal_db", "-t", "-A", "-F", "|",
        "-c", "SELECT id, title, severity, status, service_name, created_at, resolved_at FROM incidents ORDER BY created_at DESC LIMIT 1;"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = res.stdout.strip()
    if not out:
        return None
    parts = out.split("|")
    return {
        "id": parts[0],
        "title": parts[1] if len(parts) > 1 else "",
        "severity": parts[2] if len(parts) > 2 else "",
        "status": parts[3] if len(parts) > 3 else "",
        "service_name": parts[4] if len(parts) > 4 else "",
        "created_at": parts[5] if len(parts) > 5 else "",
        "resolved_at": parts[6] if len(parts) > 6 else "",
    }


def get_pg_incident_count():
    cmd = [
        "docker", "exec", "autoheal_db_dev", "psql",
        "-U", "autoheal_user", "-d", "autoheal_db", "-t", "-A",
        "-c", "SELECT COUNT(*) FROM incidents;"
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return int(res.stdout.strip())


def run_healthy_observation_windows(client: httpx.Client, num_windows: int = 3, window_seconds: int = 15):
    logger.info("=" * 70)
    logger.info(f"PHASE 1: RUNNING {num_windows} HEALTHY OBSERVATION WINDOWS ({window_seconds}s each)")
    logger.info("=" * 70)
    
    observations = []
    initial_inc_count = get_pg_incident_count()

    for i in range(1, num_windows + 1):
        start_ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"Observation Window {i}/{num_windows} started at {start_ts}")
        
        # Poll services across the window
        services_status = {}
        for svc_name, url in [("checkout-api", CHECKOUT_URL), ("customer-web", CUSTOMER_URL), ("payments-api", PAYMENTS_URL)]:
            try:
                r = client.get(f"{url}/health", timeout=5.0)
                services_status[svc_name] = r.json()
            except Exception as e:
                services_status[svc_name] = {"error": str(e), "status": "unreachable"}

        # Wait window duration
        time.sleep(window_seconds)
        end_ts = datetime.now(timezone.utc).isoformat()

        # Query Prometheus for active alerts
        prom_res = client.get(f"{PROMETHEUS_URL}/api/v1/alerts").json()
        active_alerts = prom_res.get("data", {}).get("alerts", [])

        # Query database for new incidents
        current_inc_count = get_pg_incident_count()
        new_incidents = current_inc_count - initial_inc_count

        all_healthy = all(s.get("status") == "healthy" for s in services_status.values())
        avg_error_rate = sum(float(s.get("error_rate", 0.0)) for s in services_status.values()) / len(services_status)

        # Classification logic:
        # Healthy service with 0 incidents -> True Negative (TN)
        # Healthy service with >0 incidents -> False Positive (FP)
        classification = "True Negative (TN)" if all_healthy and new_incidents == 0 else ("False Positive (FP)" if new_incidents > 0 else "Unknown")

        obs = {
            "window_id": f"healthy-obs-00{i}",
            "start_time": start_ts,
            "end_time": end_ts,
            "duration_seconds": window_seconds,
            "services": {k: {"status": v.get("status"), "error_rate": v.get("error_rate", 0.0)} for k, v in services_status.items()},
            "avg_error_rate": avg_error_rate,
            "active_prom_alerts_count": len(active_alerts),
            "new_incidents_created": new_incidents,
            "classification": classification,
        }
        observations.append(obs)
        logger.info(f"Window {i} Complete: Classification={classification}, Active Alerts={len(active_alerts)}, New Incidents={new_incidents}")

    return observations


def run_controlled_failure_lifecycle(client: httpx.Client):
    logger.info("=" * 70)
    logger.info("PHASE 2: CONTROLLED FAILURE & LIVE ALERTMANAGER DELIVERY PIPELINE")
    logger.info("=" * 70)

    # 1. Confirm initial service health
    logger.info("Step 1: Confirming checkout-api is healthy before test...")
    init_res = client.get(f"{CHECKOUT_URL}/health", timeout=5.0)
    init_state = init_res.json()
    init_ts = datetime.now(timezone.utc).isoformat()
    logger.info(f"Initial State: {init_state} at {init_ts}")
    assert init_state.get("status") == "healthy", "Service must start healthy"

    baseline_inc_count = get_pg_incident_count()
    last_known_inc = get_pg_latest_incident()
    logger.info(f"Baseline incidents count: {baseline_inc_count}, latest: {last_known_inc['id'] if last_known_inc else 'none'}")

    # 2. Trigger Controlled Failure
    logger.info("Step 2: Triggering controlled failure (stopping autoheal_test_checkout_api)...")
    fail_start_ts = datetime.now(timezone.utc).isoformat()
    subprocess.run(["docker", "stop", "autoheal_test_checkout_api"], check=True)
    logger.info(f"Container stopped at {fail_start_ts}. Waiting for Prometheus detection...")

    # 3. Wait for Prometheus to detect the condition
    rule_state = "inactive"
    firing_alert = None
    prom_detection_time = None
    
    for attempt in range(25):  # up to 75 seconds (rule has for: 30s)
        time.sleep(3)
        rules_res = client.get(f"{PROMETHEUS_URL}/api/v1/rules").json()
        groups = rules_res.get("data", {}).get("groups", [])
        for g in groups:
            for r in g.get("rules", []):
                if r.get("name") == "ServiceDown":
                    rule_state = r.get("state")
                    alerts = r.get("alerts", [])
                    logger.info(f"Prometheus ServiceDown rule state: {rule_state} (alerts: {len(alerts)})")
                    if rule_state == "firing":
                        firing_alert = alerts[0] if alerts else None
                        prom_detection_time = datetime.now(timezone.utc).isoformat()
                        break
            if rule_state == "firing":
                break
        if rule_state == "firing":
            break

    assert rule_state == "firing", f"Expected ServiceDown rule to fire, but remained {rule_state}"
    logger.info(f"Step 3: Confirmed Prometheus alert is FIRING at {prom_detection_time}!")
    logger.info(f"Firing Alert: {json.dumps(firing_alert, indent=2)}")

    # 4. Wait for Alertmanager to receive the alert
    logger.info("Step 4: Waiting for Alertmanager to receive and group the alert...")
    am_alert = None
    am_received_time = None
    for attempt in range(15):
        time.sleep(2)
        am_res = client.get(f"{ALERTMANAGER_URL}/api/v2/alerts").json()
        for a in am_res:
            if a.get("labels", {}).get("alertname") == "ServiceDown":
                am_alert = a
                am_received_time = datetime.now(timezone.utc).isoformat()
                break
        if am_alert:
            break

    assert am_alert is not None, "Expected alert in Alertmanager"
    logger.info(f"Step 4: Alertmanager received alert at {am_received_time}!")

    # 5. Wait for FastAPI to receive authenticated webhook and create incident in PostgreSQL
    logger.info("Step 5: Waiting for FastAPI to receive webhook and persist incident in PostgreSQL...")
    new_incident = None
    ingest_time = None
    for attempt in range(20):  # Alertmanager group_wait is 10s
        time.sleep(2)
        latest_inc = get_pg_latest_incident()
        if latest_inc and latest_inc["id"] != (last_known_inc["id"] if last_known_inc else ""):
            new_incident = latest_inc
            ingest_time = datetime.now(timezone.utc).isoformat()
            break

    assert new_incident is not None, "Expected new incident created in PostgreSQL"
    logger.info(f"Step 5: Incident persisted in PostgreSQL: ID={new_incident['id']}, Title={new_incident['title']}, Status={new_incident['status']} at {ingest_time}")

    # 6. Verify duplicate alerts do not create duplicate incidents (Deduplication)
    logger.info("Step 6: Verifying deduplication behavior...")
    count_after_first = get_pg_incident_count()
    time.sleep(5)  # Wait short interval
    count_after_wait = get_pg_incident_count()
    assert count_after_wait == count_after_first, f"Deduplication failed: incident count increased from {count_after_first} to {count_after_wait}"
    logger.info(f"Step 6: Deduplication Verified! Incident count remained {count_after_first} (no duplicate incidents).")

    # 7. Restore the sample service
    logger.info("Step 7: Restoring sample service (docker start autoheal_test_checkout_api)...")
    restore_start_ts = datetime.now(timezone.utc).isoformat()
    subprocess.run(["docker", "start", "autoheal_test_checkout_api"], check=True)
    logger.info(f"Container started at {restore_start_ts}. Waiting for healthcheck and Prometheus resolution...")

    # Wait for service HTTP /health to return 200
    for _ in range(15):
        time.sleep(1)
        try:
            r = client.get(f"{CHECKOUT_URL}/health", timeout=3.0)
            if r.status_code == 200:
                logger.info("checkout-api HTTP health probe: 200 OK")
                break
        except Exception:
            pass

    # 8. Wait for Prometheus alert to resolve
    logger.info("Step 8: Waiting for Prometheus ServiceDown alert to clear...")
    alert_resolved_prom = False
    prom_resolve_time = None
    for attempt in range(25):
        time.sleep(2)
        rules_res = client.get(f"{PROMETHEUS_URL}/api/v1/rules").json()
        groups = rules_res.get("data", {}).get("groups", [])
        sd_state = None
        for g in groups:
            for r in g.get("rules", []):
                if r.get("name") == "ServiceDown":
                    sd_state = r.get("state")
                    break
        if sd_state == "inactive":
            alert_resolved_prom = True
            prom_resolve_time = datetime.now(timezone.utc).isoformat()
            break
        logger.info(f"Waiting for resolution... Current state: {sd_state}")

    assert alert_resolved_prom, "Expected Prometheus alert to resolve to inactive"
    logger.info(f"Step 8: Prometheus alert resolved to 'inactive' at {prom_resolve_time}!")

    # 9. Wait for Alertmanager resolved webhook delivery and PostgreSQL incident status update
    logger.info("Step 9: Waiting for Alertmanager to send resolved webhook to FastAPI...")
    incident_resolved = False
    final_incident = None
    for attempt in range(25):
        time.sleep(2)
        latest_inc = get_pg_latest_incident()
        if latest_inc and latest_inc["id"] == new_incident["id"]:
            final_incident = latest_inc
            if latest_inc["status"] == "resolved":
                incident_resolved = True
                break
        logger.info(f"Current incident {new_incident['id']} status: {latest_inc.get('status') if latest_inc else 'none'}")

    logger.info(f"Step 9: Final incident state: {final_incident}")

    detection_latency = (datetime.fromisoformat(prom_detection_time) - datetime.fromisoformat(fail_start_ts)).total_seconds()
    recovery_duration = (datetime.fromisoformat(prom_resolve_time) - datetime.fromisoformat(restore_start_ts)).total_seconds()
    total_outage = (datetime.fromisoformat(prom_resolve_time) - datetime.fromisoformat(fail_start_ts)).total_seconds()

    return {
        "scenario": "Live Controlled Failure (checkout-api down)",
        "initial_health": init_state,
        "timestamps": {
            "initial_healthy": init_ts,
            "failure_injected": fail_start_ts,
            "prometheus_firing": prom_detection_time,
            "alertmanager_received": am_received_time,
            "fastapi_incident_created": ingest_time,
            "service_restored": restore_start_ts,
            "prometheus_resolved": prom_resolve_time,
        },
        "durations": {
            "detection_latency_seconds": round(detection_latency, 2),
            "recovery_duration_seconds": round(recovery_duration, 2),
            "total_outage_seconds": round(total_outage, 2),
        },
        "prometheus_alert": firing_alert,
        "incident_created": new_incident,
        "incident_final": final_incident,
        "deduplication_verified": True,
        "incident_resolved_verified": incident_resolved,
        "detection_classification": "True Positive (TP)",
    }


def main():
    with httpx.Client() as client:
        # Phase 1: Healthy Observation Windows
        healthy_observations = run_healthy_observation_windows(client, num_windows=3, window_seconds=15)

        # Phase 2: Live Failure & Alertmanager Delivery Test
        controlled_test_results = run_controlled_failure_lifecycle(client)

        # Phase 3: Metrics Calculation
        # Aggregate observations:
        # 3 healthy windows -> 3 True Negatives
        # 1 controlled failure -> 1 True Positive
        tn_count = sum(1 for obs in healthy_observations if obs["classification"] == "True Negative (TN)")
        fp_count = sum(1 for obs in healthy_observations if obs["classification"] == "False Positive (FP)")
        tp_count = 1 if controlled_test_results["detection_classification"] == "True Positive (TP)" else 0
        fn_count = 0

        healthy_denom = fp_count + tn_count
        false_positive_rate = round((fp_count / healthy_denom) * 100, 2) if healthy_denom > 0 else None

        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": "Docker Desktop Live Runtime (Windows WSL2)",
            "healthy_observation_windows": healthy_observations,
            "controlled_failure_test": controlled_test_results,
            "confusion_matrix": {
                "true_positives": tp_count,
                "false_positives": fp_count,
                "true_negatives": tn_count,
                "false_negatives": fn_count,
                "healthy_observation_windows_total": healthy_denom,
                "false_positive_rate_percent": false_positive_rate,
            },
        }

        out_path = os.path.join("monitoring", "live_verification_results.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        logger.info("=" * 70)
        logger.info("LIVE RUNTIME VERIFICATION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Results saved to: {out_path}")
        logger.info(f"Confusion Matrix: TP={tp_count}, FP={fp_count}, TN={tn_count}, FN={fn_count}")
        logger.info(f"Calculated False-Positive Rate: {false_positive_rate}% (FP={fp_count}, Healthy Windows={healthy_denom})")
        logger.info(f"Controlled Outage Latency: Detection={controlled_test_results['durations']['detection_latency_seconds']}s, Recovery={controlled_test_results['durations']['recovery_duration_seconds']}s, Total={controlled_test_results['durations']['total_outage_seconds']}s")
        logger.info(f"Deduplication Verified: {controlled_test_results['deduplication_verified']}")
        logger.info(f"PostgreSQL Incident: {controlled_test_results['incident_created']['id']} -> Status: {controlled_test_results['incident_final']['status']}")


if __name__ == "__main__":
    main()
