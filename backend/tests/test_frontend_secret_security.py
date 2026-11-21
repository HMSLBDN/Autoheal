"""
AutoHeal DevOps — Frontend Secret Exposure & Webhook Boundary Security Tests

Verifies that webhook secrets, signing keys, and server-side credentials:
1. Are never present or referenced in any frontend code (app/, components/, lib/, types/, public/).
2. Are not exposed via NEXT_PUBLIC_* environment variables.
3. Are never stored in browser storage (localStorage, sessionStorage).
4. Do not leak into compiled production Next.js bundles.
5. Remain strictly server-side, with the backend failing closed on unauthorized webhook requests.
"""

import os
from pathlib import Path
import re
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.config import get_settings
from app.main import app
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIRS = [
    REPO_ROOT / "app",
    REPO_ROOT / "components",
    REPO_ROOT / "lib",
    REPO_ROOT / "types",
    REPO_ROOT / "public",
]

SENSITIVE_PATTERNS = [
    re.compile(r"ALERTMANAGER_HMAC_SECRET", re.IGNORECASE),
    re.compile(r"NEXT_PUBLIC_ALERTMANAGER_SECRET", re.IGNORECASE),
    re.compile(r"autoheal_alertmanager_webhook_hmac_secret_key_12345", re.IGNORECASE),
    re.compile(r"autoheal_dev_alertmanager_webhook_secret_32chars", re.IGNORECASE),
]

DISALLOWED_NEXT_PUBLIC_PATTERNS = [
    re.compile(r"NEXT_PUBLIC_.*(?:SECRET|KEY|TOKEN|PASSWORD|HMAC|PRIVATE|CREDENTIAL)", re.IGNORECASE)
]

ALLOWED_NEXT_PUBLIC_VARS = {
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_DEMO_MODE",
}


def _collect_frontend_files():
    """Gathers all frontend source code files (.ts, .tsx, .js, .jsx, .json)."""
    files = []
    for fdir in FRONTEND_DIRS:
        if fdir.exists():
            for p in fdir.rglob("*"):
                if p.is_file() and p.suffix in (".ts", ".tsx", ".js", ".jsx", ".json", ".mjs"):
                    files.append(p)
    return files


def test_no_webhook_secrets_or_hmac_in_frontend_source():
    """Ensure no frontend source file contains references to Alertmanager webhook secrets."""
    frontend_files = _collect_frontend_files()
    assert len(frontend_files) > 0, "Frontend source files must be discoverable"

    violations = []
    for fpath in frontend_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pattern in SENSITIVE_PATTERNS:
            match = pattern.search(content)
            if match:
                rel_path = fpath.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}: matched sensitive pattern '{pattern.pattern}'")

    assert not violations, f"Sensitive credentials found in frontend source files:\n" + "\n".join(violations)


def test_no_alerts_api_in_frontend_resources():
    """Verify alertsApi or client-side webhook dispatching does not exist in lib/api/resources.ts."""
    resources_file = REPO_ROOT / "lib" / "api" / "resources.ts"
    assert resources_file.exists(), "lib/api/resources.ts must exist"
    content = resources_file.read_text(encoding="utf-8")

    assert "alertsApi" not in content, "alertsApi must be completely removed from lib/api/resources.ts"
    assert "NEXT_PUBLIC_ALERTMANAGER_SECRET" not in content, "NEXT_PUBLIC_ALERTMANAGER_SECRET must not exist"
    assert "/api/v1/alerts/webhook" not in content, "Webhook path must not be called from frontend client"


def test_next_public_environment_variable_allowlist():
    """
    Ensure that ONLY explicitly allowlisted non-sensitive NEXT_PUBLIC_* variables
    are referenced in frontend code.
    """
    frontend_files = _collect_frontend_files()
    next_public_regex = re.compile(r"process\.env\.(NEXT_PUBLIC_[A-Z0-9_]+)")

    discovered_vars = set()
    violations = []

    for fpath in frontend_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in next_public_regex.finditer(content):
            var_name = match.group(1)
            discovered_vars.add(var_name)
            if var_name not in ALLOWED_NEXT_PUBLIC_VARS:
                rel_path = fpath.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}: unauthorized NEXT_PUBLIC variable '{var_name}'")

            for dis_pat in DISALLOWED_NEXT_PUBLIC_PATTERNS:
                if dis_pat.search(var_name):
                    rel_path = fpath.relative_to(REPO_ROOT)
                    violations.append(f"{rel_path}: NEXT_PUBLIC variable '{var_name}' contains sensitive token")

    assert not violations, (
        f"Prohibited NEXT_PUBLIC_* variables detected:\n"
        + "\n".join(violations)
        + f"\nAllowed: {sorted(ALLOWED_NEXT_PUBLIC_VARS)}"
    )


def test_browser_storage_does_not_contain_secrets():
    """Verify localStorage / sessionStorage usage only stores standard auth tokens, never webhook secrets."""
    frontend_files = _collect_frontend_files()
    storage_regex = re.compile(r"(?:localStorage|sessionStorage)\.setItem\s*\(\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)

    allowed_storage_keys = {
        "autoheal_access_token",
        "autoheal_user",
    }

    violations = []
    for fpath in frontend_files:
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for match in storage_regex.finditer(content):
            key_name = match.group(1)
            if key_name not in allowed_storage_keys:
                rel_path = fpath.relative_to(REPO_ROOT)
                violations.append(f"{rel_path}: unexpected storage key '{key_name}'")

    assert not violations, f"Unexpected browser storage keys found:\n" + "\n".join(violations)


@pytest.mark.asyncio
async def test_alertmanager_webhook_fails_closed_without_server_secret(db_session: AsyncSession):
    """
    Backend webhook endpoint /api/v1/alerts/webhook must fail closed with 401 Unauthorized
    when called without valid server-side credentials.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            payload = {
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {"alertname": "TestAlert", "service": "checkout-api"},
                    }
                ],
            }

            # 1. No auth headers
            res_no_auth = client.post("/api/v1/alerts/webhook", json=payload)
            assert res_no_auth.status_code == 401

            # 2. Invalid Bearer token
            res_bad_bearer = client.post(
                "/api/v1/alerts/webhook",
                json=payload,
                headers={"Authorization": "Bearer completely_invalid_token_123"},
            )
            assert res_bad_bearer.status_code == 401

            # 3. Invalid X-Alertmanager-Secret
            res_bad_secret = client.post(
                "/api/v1/alerts/webhook",
                json=payload,
                headers={"X-Alertmanager-Secret": "invalid_secret_value"},
            )
            assert res_bad_secret.status_code == 401

            # 4. Valid server-configured secret succeeds
            res_valid = client.post(
                "/api/v1/alerts/webhook",
                json=payload,
                headers={"Authorization": f"Bearer {settings.ALERTMANAGER_HMAC_SECRET}"},
            )
            assert res_valid.status_code == 200
            assert res_valid.json()["status"] == "success"
    finally:
        app.dependency_overrides.clear()


def test_compiled_production_bundle_contains_no_webhook_secrets():
    """
    If .next build output exists, inspect compiled chunks to verify zero secret strings
    leak into client bundles.
    """
    next_static_dir = REPO_ROOT / ".next" / "static"
    if not next_static_dir.exists():
        pytest.skip(".next/static does not exist; run production build before this test")

    secret_strings_to_check = [
        "autoheal_alertmanager_webhook_hmac_secret_key_12345",
        "autoheal_dev_alertmanager_webhook_secret_32chars",
        "NEXT_PUBLIC_ALERTMANAGER_SECRET",
    ]

    violations = []
    for js_file in next_static_dir.rglob("*.js"):
        try:
            content = js_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for sec in secret_strings_to_check:
            if sec in content:
                violations.append(f"{js_file.name}: contains secret token '{sec}'")

    assert not violations, f"Production JavaScript bundle contains leaked secret strings:\n" + "\n".join(violations)
