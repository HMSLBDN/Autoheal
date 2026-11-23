# AutoHeal DevOps — Alembic Path Configuration Repair Report

**Date:** November 23, 2026  
**Repository:** `https://github.com/HMSLBDN/Autoheal.git`  
**Working Directory:** `c:\Users\Akshay N\Documents\Autoheal\autoheal-devops-saas`  
**Configuration File:** `backend/alembic.ini`  
**Migration Directory:** `backend/alembic`  
**Migration Runner:** `migrate_production.ps1`  

---

## 1. Problem Diagnosis

When executing `migrate_production.ps1` from the repository root, Alembic failed with:

```text
FAILED: Path doesn't exist: 'C:\Users\Akshay N\Documents\Autoheal\autoheal-devops-saas\alembic'.
Please use the 'init' command to create a new scripts folder.
```

### Root Cause:
* In `backend/alembic.ini`, line 5 was configured with a relative path:
  ```ini
  script_location = alembic
  ```
* When Alembic is invoked from the repository root (`-c backend/alembic.ini`), it resolved `alembic` relative to the current process working directory (`$CWD/alembic`), attempting to find `C:\Users\Akshay N\Documents\Autoheal\autoheal-devops-saas\alembic` instead of `backend/alembic`.

---

## 2. Corrections Implemented

### 1. `backend/alembic.ini`
Updated `script_location` to use Alembic's built-in `%(here)s` variable:
```ini
[alembic]
# path to migration scripts (anchored to the directory containing alembic.ini)
script_location = %(here)s/alembic
```
* `%(here)s` resolves dynamically to the directory where `alembic.ini` resides (`backend/`).
* Alembic now resolves the migration scripts to `backend/alembic/` regardless of whether the command is run from the project root, the `backend` folder, or any other directory.

### 2. `migrate_production.ps1`
Hardened path handling in the migration runner:
* Automatically anchors working directory to `$ScriptDir` (project root).
* Uses absolute paths for `$backendDir` and `$iniPath = Join-Path $backendDir "alembic.ini"`.
* Sets `$env:PYTHONPATH = $backendDir`.
* Passes explicit `$iniPath` to all Alembic CLI commands:
  * `& $pyExe -m alembic -c $iniPath current`
  * `& $pyExe -m alembic -c $iniPath upgrade head`
  * `& $pyExe -m alembic -c $iniPath current`
* Preserves zero-credential-exposure in-memory processing (`Read-Host -AsSecureString`).
* Preserves database URL normalization helper (`prepare_database_url_and_args`).
* Preserves target host `.neon.tech` validation.
* Preserves post-migration verification of all 43 tables.

---

## 3. Validation & Discovery Results

Both validation commands were executed from the repository root:

### 1. `python -m alembic -c backend/alembic.ini heads`
```text
0010_add_phase16_recovery_classification (head)
```
* **Exit Code:** `0` (Success)
* Correctly discovers the target migration head.

### 2. `python -m alembic -c backend/alembic.ini history`
```text
0009_add_phase14_experiment_tables -> 0010_add_phase16_recovery_classification (head), Add Phase 16 recovery execution mode and evidence classification
0008_add_phase13_pilot_tables -> 0009_add_phase14_experiment_tables, Add Phase 14 experiment and benchmark evaluation tables
0007_add_phase10_security_tables -> 0008_add_phase13_pilot_tables, Add Phase 13 organization invitations and incident lifecycle transition records
0006_add_phase9_enterprise_tables -> 0007_add_phase10_security_tables, Add Phase 10 enterprise security, SSO, user sessions, audit events, and agent mTLS certificates
0005_add_phase8_intelligence_tables -> 0006_add_phase9_enterprise_tables, Add Phase 9 enterprise notifications, webhooks, incident collaboration, escalations, and canary release tables
0004_add_infrastructure_agents_table -> 0005_add_phase8_intelligence_tables, Add Phase 8 intelligence, anomaly detection, predictions, and risk scoring tables
0003_add_production_performance_indexes -> 0004_add_infrastructure_agents_table, Add infrastructure_agents table and indexes
0002_add_password_resets -> 0003_add_production_performance_indexes, Add production composite performance indexes
0001_initial_schema -> 0002_add_password_resets, Add password_resets table for secure self-service password recovery
<base> -> 0001_initial_schema, Initial database schema: 15 core AutoHeal tables
```
* **Exit Code:** `0` (Success)
* The entire 10-revision migration chain is resolved and verified.

---

## 4. Current Status

* **Status:** **REPAIRED AND VALIDATED**
* **Strict Stop Observed:** `upgrade head` has **NOT** been executed.
* **Ready for User Run:** You can now run `.\migrate_production.ps1` in your integrated terminal.
