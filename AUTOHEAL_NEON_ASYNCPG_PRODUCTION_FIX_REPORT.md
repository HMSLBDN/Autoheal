# AutoHeal DevOps — Neon Asyncpg PostgreSQL Connection Fix Report

**Generated:** November 23, 2026  
**Environment:** Production / Vercel Serverless  
**Target:** https://autoheal-omega.vercel.app  
**Repository:** `HMSLBDN/Autoheal`  
**Branch:** `main`  

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 The Incident
During production user registration (`POST /api/v1/auth/register`), the endpoint failed with an HTTP 500 error (`req-d1c8c960a006`).
Vercel function runtime logs captured the exact traceback:

```text
TypeError: connect() got an unexpected keyword argument 'channel_binding'
  File "backend/app/api/routes/auth.py", line 112, in register
    existing_user = await db.scalar(select(User).where(User.email == user_in.email))
  ...
  File "sqlalchemy/dialects/postgresql/asyncpg.py", line 950, in create_connect_args
    return ([], cparams)
  File "asyncpg/connection.py", line 2344, in connect
    return await connect_utils._connect(...)
```

### 1.2 Root Cause
1. **Neon PostgreSQL Default Query Parameters**:
   Neon generates default connection strings that include libpq-specific connection options such as:
   `?sslmode=require&channel_binding=require` (and in some setups, `&endpoint=ep-xyz`).
2. **SQLAlchemy Asyncpg Dialect Argument Unpacking**:
   SQLAlchemy's `postgresql+asyncpg` dialect parses all query parameters from the URL and passes them as keyword arguments (`cparams`) to `asyncpg.connect(**cparams)`.
3. **Asyncpg Parameter Strictness**:
   `asyncpg` is an independent, pure-Python / Cython PostgreSQL driver and is **not** based on libpq. Its `asyncpg.connect()` function explicitly accepts only its supported parameters (`host`, `port`, `user`, `password`, `database`, `ssl`, `statement_cache_size`, `timeout`, `command_timeout`, `server_settings`, `target_session_attrs`, etc.).
   When `channel_binding` or other libpq-only parameters are present in the URL query string, `asyncpg.connect()` rejects them with a fatal `TypeError: connect() got an unexpected keyword argument 'channel_binding'`, completely preventing database socket creation.

---

## 2. Solution: Robust Connection Normalization Layer

To permanently eliminate this issue without requiring manual connection string stripping across developer machines and cloud environments, a robust, automated URL normalization layer was implemented directly within the core application configuration and Alembic migration loader.

### 2.1 Implementation Details

#### 1. [backend/app/config.py](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/backend/app/config.py)
In `Settings.assemble_database_url`:
- **Whitespace Sanitation**: Strips leading and trailing whitespace from input connection strings.
- **SQLite Passthrough**: Detects and preserves local/testing SQLite URLs (e.g. `sqlite+aiosqlite:///:memory:`) completely untouched.
- **Driver Standardization**: Converts legacy `postgres://` and standard `postgresql://` schemes to `postgresql+asyncpg://`.
- **SSL Translation**: Translates libpq's `sslmode=<mode>` to asyncpg's expected `ssl=<mode>`. Validates against permitted modes (`disable`, `prefer`, `require`, `verify-ca`, `verify-full`).
- **Libpq Parameter Filtering**: Identifies and removes libpq-only query parameters that cause `TypeError` in `asyncpg.connect()`:
  - `channel_binding`
  - `endpoint`
  - `connect_timeout`
  - `keepalives`
  - `keepalives_idle`
  - `keepalives_interval`
  - `keepalives_count`
  - `tcp_user_timeout`
  - `gssencmode`
  - `target_session_attrs`
- **Application Parameter Retention**: Preserves application-level query parameters (e.g., `application_name=autoheal`) and asyncpg-supported parameters.
- **Special Character Safety**: Uses SQLAlchemy's `make_url` and `render_as_string(hide_password=False)` to guarantee credentials containing URL-encoded characters (e.g., `%40`, `#`, `$`) remain completely intact.

#### 2. [backend/alembic/env.py](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/backend/alembic/env.py)
Updated Alembic migration configuration to route raw `DATABASE_URL` through `settings.assemble_database_url()` before setting `sqlalchemy.url`. This ensures CLI and serverless migration runs benefit from the exact same sanitization and driver adaptation.

#### 3. [backend/tests/test_database_url_normalization.py](file:///c:/Users/Akshay%20N/Documents/Autoheal/autoheal-devops-saas/backend/tests/test_database_url_normalization.py)
Created a dedicated test suite with 8 exhaustive test cases:
- `test_neon_url_with_channel_binding_and_sslmode`: Verifies `channel_binding` is stripped and `sslmode=require` -> `ssl=require`.
- `test_neon_pooled_connection_url`: Verifies pooled connection hostnames (`ep-silent-shadow-pooler...`) and parameters are sanitized without host corruption.
- `test_url_with_all_libpq_unsupported_params`: Verifies all 10 libpq parameters are stripped in a single complex string.
- `test_credentials_with_special_characters`: Verifies passwords with symbols (`p@ss#word%21`) remain correctly encoded.
- `test_standard_postgresql_url`: Verifies standard local URLs are properly prefixed with `+asyncpg`.
- `test_sqlite_urls_untouched`: Verifies memory and file SQLite paths are untouched.
- `test_invalid_sslmode_rejected`: Verifies invalid `sslmode` values trigger validation errors.
- `test_asyncpg_engine_creation_with_normalized_url`: Directly initializes an `AsyncEngine` with a normalized Neon URL and verifies the dialect connect arguments contain no forbidden keys.

---

## 3. Verification & Quality Gates

### 3.1 Python Unit and Regression Suites
All tests passed with zero errors or warnings:

```bash
pytest backend/tests/test_database_url_normalization.py backend/tests/test_database_ssl_security.py -v
# Output: 18 passed in 1.48s

pytest backend/tests/test_database_url_normalization.py \
       backend/tests/test_phase27_comprehensive_auth.py \
       backend/tests/test_phase22_auth_integration.py \
       backend/tests/test_phase22b_deployment_readiness.py \
       backend/tests/test_auth.py \
       backend/tests/test_auth_security.py \
       backend/tests/test_database_ssl_security.py \
       backend/tests/test_sse_ticket_security.py -q
# Output: 70 passed in 7.80s
```

### 3.2 Python Bytecode Compilation
```bash
python -m compileall backend/app backend/tests
# Output: 0 errors
```

### 3.3 Frontend Validation Gates
- **TypeScript Typecheck**:
  ```bash
  npx tsc --noEmit
  # Output: 0 errors
  ```
- **ESLint**:
  ```bash
  npm run lint
  # Output: 0 errors
  ```
- **Next.js Production Build**:
  ```bash
  npm run build
  # Output: Compiled successfully in 2.9s. All routes generated. Build trace collected.
  ```

---

## 4. Modified and Untracked Files

### Modified Files:
1. `backend/app/config.py`: Implemented robust `assemble_database_url` validator.
2. `backend/alembic/env.py`: Integrated `assemble_database_url` for Alembic migrations.

### New Test File:
1. `backend/tests/test_database_url_normalization.py`: Unit test suite covering all URL edge cases.

---

## 5. Security & Safety Compliance

- [x] **No Secret Leaks**: No credentials, passwords, or live connection strings were printed or committed.
- [x] **Safety Flags Intact**:
  - `RECOVERY_SIMULATION_MODE=true` confirmed.
  - `RESTRICTED_DOCKER_AGENT_ENABLED=false` confirmed.
- [x] **No Cloud Resources Mutated**: No direct mutations to Vercel production or Neon cloud projects were executed.
- [x] **No Unauthorized Git Actions**: No staging, commits, or pushes were performed.

---

## 6. Next Steps & Redeployment Instructions

Once authorized to commit and push to `origin main`:

1. **Stage and Commit Authorized Files**:
   - `backend/app/config.py`
   - `backend/alembic/env.py`
   - `backend/tests/test_database_url_normalization.py`
   - Commit message: `fix(database): sanitize libpq connection parameters for asyncpg dialect`

2. **Push to GitHub**:
   - Push to `HMSLBDN/Autoheal` on branch `main`.

3. **Vercel Automatic Redeployment**:
   - Vercel will trigger a new deployment for `autoheal-omega`.
   - Vercel's Python runtime will build using the updated `assemble_database_url` validator.
   - Any Neon connection string containing `channel_binding=require` will automatically be sanitized into a clean `asyncpg`-compatible URL.

4. **Verify Live Registration**:
   - Navigate to `https://autoheal-omega.vercel.app/register`.
   - Submit user registration.
   - Confirm HTTP 201 Created and successful redirect to onboarding or dashboard.
