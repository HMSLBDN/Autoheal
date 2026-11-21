# PostgreSQL Migration Evidence

**Suite:** Alembic Async Migrations  
**Target:** Live PostgreSQL 16  
**Timestamp:** 2026-11-21T19:27:32+05:30  
**Head Revision:** `0007_add_phase10_security_tables`  
**Execution Duration:** **1.378 seconds**  
**Status:** **VERIFIED**  

---

## 1. Migration Sequence & Lineage

The database schema was executed against an empty disposable database and the base database, covering all 7 migration revisions:

```text
[alembic.runtime.migration] Context impl PostgresqlImpl.
[alembic.runtime.migration] Will assume transactional DDL.
[alembic.runtime.migration] Running upgrade  -> 0001_initial_schema
[alembic.runtime.migration] Running upgrade 0001_initial_schema -> 0002_add_password_resets
[alembic.runtime.migration] Running upgrade 0002_add_password_resets -> 0003_add_production_performance_indexes
[alembic.runtime.migration] Running upgrade 0003_add_production_performance_indexes -> 0004_add_infrastructure_agents_table
[alembic.runtime.migration] Running upgrade 0004_add_infrastructure_agents_table -> 0005_add_phase8_intelligence_tables
[alembic.runtime.migration] Running upgrade 0005_add_phase8_intelligence_tables -> 0006_add_phase9_enterprise_tables
[alembic.runtime.migration] Running upgrade 0006_add_phase9_enterprise_tables -> 0007_add_phase10_security_tables
```

---

## 2. Verified Relational Schema

### Summary Statistics
- **Total Relational Tables:** `40`
- **Total Indexes (Primary & Composite):** `169`
- **Total Foreign Key Constraints:** `65`

### Complete Table Manifest
1. `agent_certificates`
2. `alembic_version`
3. `alert_configs`
4. `anomaly_events`
5. `audit_logs`
6. `deployment_events`
7. `escalation_events`
8. `escalation_policies`
9. `identity_provider_configs`
10. `incident_assignments`
11. `incident_comments`
12. `incident_correlations`
13. `incident_events`
14. `incident_evidence`
15. `incidents`
16. `infrastructure_agents`
17. `model_evaluation_records`
18. `notification_channels`
19. `notification_deliveries`
20. `notification_subscriptions`
21. `organizations`
22. `password_resets`
23. `predictive_insights`
24. `preventive_recommendations`
25. `recovery_actions`
26. `recovery_policies`
27. `recovery_results`
28. `refresh_tokens`
29. `release_evaluation_metrics`
30. `release_evaluations`
31. `security_audit_events`
32. `service_metrics`
33. `service_monitors`
34. `service_risk_scores`
35. `services`
36. `user_identity_mappings`
37. `user_sessions`
38. `users`
39. `webhook_delivery_attempts`
40. `webhook_endpoints`

---

## 3. Engineering Fix: Alembic Revision Length Extension

During migration execution, Alembic 1.14 default `alembic_version` was hardcoded to `VARCHAR(32)`. Revisions longer than 32 characters (e.g., `0003_add_production_performance_indexes`, 40 chars) failed with `StringDataRightTruncationError`.

### Resolution Implemented:
1. Updated `backend/alembic/env.py` to override `PostgresqlImpl.version_table_impl` with `Column("version_num", String(128))`.
2. Added `ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);` in `0003_add_production_performance_indexes.py`.
3. Verified subsequent migrations execute with exit code 0.
