# AutoHeal DevOps — Backend & Database Documentation

## 1. Overview
The AutoHeal DevOps backend is powered by **Python 3.12**, **FastAPI**, and **SQLAlchemy 2.0 (AsyncIO)** with **PostgreSQL 16**.
It provides multi-tenant data isolation, strict telemetry ingestion, policy-governed self-healing workflows, and full compatibility with the existing Next.js 16 frontend.

---

## 2. Environment Configuration
Copy `.env.example` from the repository root to create your local `.env`:
```bash
cp .env.example .env
```

Key database environment variables:
| Variable | Description | Default |
| :--- | :--- | :--- |
| `DATABASE_URL` | Async PostgreSQL connection URI | `postgresql+asyncpg://autoheal_user:autoheal_dev_password@localhost:5432/autoheal_db` |
| `DEFAULT_ORGANIZATION_SLUG` | Multi-tenant organization slug | `autoheal-workspace` |
| `DEFAULT_ORGANIZATION_NAME` | Default workspace display name | `AutoHeal Workspace` |
| `INITIAL_ADMIN_EMAIL` | Optional initial admin user email | (Empty / Not set) |
| `INITIAL_ADMIN_PASSWORD` | Optional initial admin password | (Empty / Not set) |

> **Security Note**: Never commit `.env` or hardcode production passwords.

---

## 3. PostgreSQL Database Setup

### Local Docker Setup (Recommended)
Start PostgreSQL using Docker:
```bash
docker run --name autoheal-postgres \
  -e POSTGRES_DB=autoheal_db \
  -e POSTGRES_USER=autoheal_user \
  -e POSTGRES_PASSWORD=autoheal_dev_password \
  -p 5432:5432 -d postgres:16-alpine
```

### Native PostgreSQL Setup
Create the database and user in `psql`:
```sql
CREATE USER autoheal_user WITH PASSWORD 'autoheal_dev_password';
CREATE DATABASE autoheal_db OWNER autoheal_user;
GRANT ALL PRIVILEGES ON DATABASE autoheal_db TO autoheal_user;
```

---

## 4. Alembic Migrations

Migrations are configured in `backend/alembic.ini` and `backend/alembic/`.

### Run Migrations (Upgrade to Head)
```bash
# From repository root or backend directory:
alembic -c backend/alembic.ini upgrade head
```

### Roll Back the Most Recent Migration
```bash
alembic -c backend/alembic.ini downgrade -1
```

### Roll Back to Base (Wipe All Tables)
```bash
alembic -c backend/alembic.ini downgrade base
```

### Offline Migration Verification (Dry Run)
Generate the migration SQL without requiring a live database:
```bash
alembic -c backend/alembic.ini upgrade head --sql
```

---

## 5. Running the Database Seeder
The database seeder is idempotent. Executing it multiple times will not create duplicate records:
```bash
python backend/seed.py
```
To seed an initial admin account, pass environment variables during execution:
```bash
INITIAL_ADMIN_EMAIL="admin@autoheal.dev" INITIAL_ADMIN_PASSWORD="SecureAdminPassword123!" python backend/seed.py
```

---

## 6. Database Entity Relationship Overview

The schema organizes data into 15 normalized tables across five logical domains:

### A. Organization & Access Domain
1. **`organizations`**: Multi-tenant workspace boundary.
2. **`users`**: User accounts with RBAC roles (`admin`, `operator`, `viewer`) and Argon2id password hashes.
3. **`refresh_tokens`**: Refresh token rotation (RTR) tracking with family-based replay attack detection.

### B. Service & Monitoring Domain
4. **`services`**: Monitored microservices matching the frontend `Service` contract.
5. **`service_monitors`**: Health check and `/metrics` scrape intervals and endpoints.
6. **`alert_configs`**: Threshold configurations and alerting rules.
7. **`deployment_events`**: Release events correlated with telemetry spikes.
8. **`recovery_policies`**: Governed allowlisted action rules, cooldowns (default 15m), and retry limits.

### C. Incident & Evidence Domain
9. **`incidents`**: Incident records, severity, AI probable cause, and recommended remedy.
10. **`incident_evidence`**: Correlated evidence items (metrics, logs, deployment diffs, health probes).
11. **`incident_events`**: Historical progression timeline events.

### D. Recovery Domain
12. **`recovery_actions`**: Recovery queue and historical execution records (`pending_approval`, `approved`, `running`, `completed`, `failed`, `rejected`).
13. **`recovery_results`**: Post-recovery verification outcomes and diagnostic logs.

### E. Telemetry & Governance Domain
14. **`service_metrics`**: Time-series metric samples (CPU, memory, request rate, latency, availability).
15. **`audit_logs`**: Immutable audit logs capturing every user action and policy evaluation.
