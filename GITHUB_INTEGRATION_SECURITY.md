# AutoHeal DevOps — GitHub Actions Integration & CI/CD Security Guide

## 1. Overview

AutoHeal employs a hardened GitHub Actions CI/CD pipeline across 4 isolated verification jobs:
1. `backend-lint-and-typecheck`: Flake8 linting and Python static analysis.
2. `backend-tests`: Full Pytest suite with PostgreSQL and Redis test containers.
3. `frontend-lint-and-typecheck`: ESLint and TypeScript compilation (`tsc --noEmit`).
4. `frontend-build`: Production Next.js optimized compilation.

---

## 2. CI/CD Security Hardening Policies

### 1. Zero Plaintext Secret Exposure
- No credentials or API keys are committed to repository tracking.
- Webhook secrets, database connection strings, and JWT signing keys are injected via GitHub Repository Secrets (`secrets.ALERTMANAGER_SECRET`, `secrets.JWT_SECRET`).
- Frontend builds contain zero secret references; only explicitly public endpoints (`NEXT_PUBLIC_API_BASE_URL`) are present.

### 2. Least Privilege Token Permissions
Workflows specify explicit minimal token scopes:
```yaml
permissions:
  contents: read
  packages: read
  statuses: write
```
Elevated permissions (`id-token: write`, `pull-requests: write`) are strictly forbidden on main branch pushes.

### 3. Hermetic Dependency Management
- Python dependencies are pinned in `backend/requirements.txt` with exact hashes.
- Frontend dependencies use clean installs via `npm ci` with `package-lock.json` integrity validation.

---

## 3. Pull Request & Commit Verification Checklist

Before pushing commits to `main`:
1. `python -m compileall -q backend/app backend/tests scripts` returns 0.
2. `pytest backend/tests -v` reports 100% pass rate.
3. `npx tsc --noEmit` and `npx eslint .` return 0 errors.
4. `npm run build` succeeds without warnings.
5. All 4 GitHub Actions jobs report SUCCESS.
