# AutoHeal DevOps — PostgreSQL Production Operations & Hardening Manual

## 1. Overview & Operational Objectives

The persistence tier of AutoHeal DevOps SaaS is engineered on **PostgreSQL 16+**, providing ACID-compliant multi-tenant isolation, structured JSONB indexing for observability evidence, and sub-second transaction performance.

This manual outlines production hardening standards, connection pooling strategies, maintenance routines, and replication architectures.

---

## 2. Connection Pool Hardening

In high-concurrency environments, unbounded database connections cause CPU context switching overhead and memory starvation. AutoHeal enforces connection pooling across application engines and external poolers.

### 2.1 SQLAlchemy AsyncEngine Configuration (`backend/app/database.py`)

```python
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,
    future=True,
    pool_size=20,            # Base persistent connections
    max_overflow=10,         # Burst capacity for high traffic spikes
    pool_timeout=30,         # Maximum seconds to wait for a connection
    pool_recycle=1800,       # Recycle connections every 30 minutes to prevent stale sockets
    pool_pre_ping=True,      # Emit 'SELECT 1' test ping to discard dropped TCP connections
)
```

### 2.2 PgBouncer Recommended Configuration

In enterprise deployments, PgBouncer is placed in front of PostgreSQL in **Transaction Pooling Mode**:

```ini
[databases]
autoheal_prod = host=127.0.0.1 port=5432 dbname=autoheal_prod pool_size=50

[pgbouncer]
listen_port = 6432
listen_addr = *
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 10
reserve_pool_size = 5
reserve_pool_timeout = 5
max_db_connections = 100
server_idle_timeout = 600
server_connect_timeout = 15
server_login_retry = 15
client_login_timeout = 60
```

---

## 3. Storage & Indexing Strategy

### 3.1 Multi-Tenant Composite Indexes

All queries must enforce tenant isolation by filtering on `organization_id`. The following composite B-tree indexes are maintained:

```sql
-- Incidents by Tenant & Status
CREATE INDEX ix_incidents_org_status ON incidents (organization_id, status);

-- Remediation Actions by Incident & Execution Status
CREATE INDEX ix_actions_incident_status ON remediation_actions (incident_id, status);

-- Active User Sessions
CREATE INDEX ix_user_sessions_org_user ON user_sessions (organization_id, user_id) WHERE is_active = TRUE;

-- Infrastructure Agents by Environment
CREATE INDEX ix_agents_org_env ON infrastructure_agents (organization_id, environment);

-- Security Audit Events by Timestamp
CREATE INDEX ix_audit_org_timestamp ON security_audit_events (organization_id, timestamp DESC);
```

### 3.2 JSONB Telemetry Indexing

Alertmanager payloads, Gemini diagnostic rationale, and execution logs utilize PostgreSQL `JSONB` columns with GIN indexes:

```sql
CREATE INDEX ix_incidents_evidence_gin ON incidents USING GIN (evidence_json jsonb_path_ops);
```

---

## 4. Routine Maintenance & Vacuum Automation

AutoHeal schedules non-blocking autovacuum routines configured in `postgresql.conf`:

```conf
# Autovacuum Tuning for High-Write SaaS Tables
autovacuum = on
autovacuum_max_workers = 4
autovacuum_naptime = 1min
autovacuum_vacuum_threshold = 50
autovacuum_analyze_threshold = 50
autovacuum_vacuum_scale_factor = 0.05
autovacuum_analyze_scale_factor = 0.02
autovacuum_vacuum_cost_limit = 1000
autovacuum_vacuum_cost_delay = 2ms

# Work Memory & Buffer Cache
shared_buffers = 4GB                 # 25% of total system RAM
work_mem = 64MB                      # Per-query sort buffer
maintenance_work_mem = 512MB         # Autovacuum maintenance RAM
effective_cache_size = 12GB          # 75% of total system RAM
```

---

## 5. Security & TLS Configuration

1. **SCRAM-SHA-256 Authentication**: Plaintext or MD5 passwords are strictly prohibited. `password_encryption = scram-sha-256` is enforced in `pg_hba.conf`.
2. **Mandatory TLS Encryption**: Connections require `ssl = on` with TLS 1.3 preferred.
3. **Role Segregation**:
   - `autoheal_app`: DML permissions (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) on application tables. No `DROP` or `ALTER` permissions.
   - `autoheal_migration`: Used exclusively by Alembic for schema migrations during controlled CI/CD deployments.
   - `autoheal_backup`: Scoped read-only role with `pg_read_all_data` for logical backups.
