"""
AutoHeal DevOps — Non-Destructive Database Connectivity Diagnostic Suite
Tests DNS, TCP port 5432, TLS/asyncpg connection, SELECT 1, and Alembic revision.
Never exposes credentials and never executes schema migrations.
"""

import asyncio
import json
import socket
import sys
import time
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import prepare_database_url_and_args, ensure_neon_dns_fallback


def run_dns_check(host: str, port: int = 5432) -> Dict[str, Any]:
    """Tests system DNS and fallback public DNS (8.8.8.8 / 1.1.1.1)."""
    # 1. System DNS
    try:
        results = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        ips = sorted(list(set(r[4][0] for r in results)))
        if ips:
            return {
                "success": True,
                "mode": "system",
                "resolved_ips": ips,
                "primary_ip": ips[0],
                "message": f"Resolved by system DNS to {', '.join(ips)}",
            }
    except socket.gaierror as exc:
        system_err = str(exc)
    except Exception as exc:
        system_err = str(exc)

    # 2. Public DNS Fallback
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
        resolver.timeout = 4.0
        resolver.lifetime = 4.0
        answers = resolver.resolve(host, "A")
        ips = [a.address for a in answers]
        if ips:
            return {
                "success": True,
                "mode": "public_fallback",
                "resolved_ips": ips,
                "primary_ip": ips[0],
                "message": (
                    f"Resolved via public DNS (8.8.8.8) to {', '.join(ips)}. "
                    "(Note: local network DNS returned query refused; fallback DNS resolved successfully)"
                ),
            }
    except Exception as exc:
        fallback_err = str(exc)

    return {
        "success": False,
        "mode": "failed",
        "resolved_ips": [],
        "primary_ip": None,
        "message": f"DNS resolution failed. System DNS: {system_err}. Fallback DNS: {fallback_err}",
    }


def run_tcp_check(target_ip: str, port: int = 5432, timeout_seconds: float = 5.0) -> Dict[str, Any]:
    """Tests raw TCP socket connectivity to port 5432."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_seconds)
    t0 = time.time()
    try:
        sock.connect((target_ip, port))
        latency_ms = round((time.time() - t0) * 1000, 1)
        sock.close()
        return {
            "success": True,
            "latency_ms": latency_ms,
            "message": f"Connected to {target_ip}:{port} in {latency_ms}ms",
        }
    except socket.timeout:
        return {
            "success": False,
            "latency_ms": None,
            "message": f"Connection to {target_ip}:{port} timed out after {timeout_seconds}s (port filtered or unreachable)",
        }
    except Exception as exc:
        return {
            "success": False,
            "latency_ms": None,
            "message": f"TCP connection to {target_ip}:{port} failed: {exc}",
        }


async def run_async_database_checks(clean_url: str, extra_kwargs: dict) -> Dict[str, Any]:
    """
    Connects to PostgreSQL using asyncpg, executes SELECT 1, and queries Alembic version.
    """
    engine_kwargs = {"echo": False}
    if "connect_args" in extra_kwargs:
        engine_kwargs["connect_args"] = dict(extra_kwargs["connect_args"])

    # Ensure connection timeout is bounded
    engine_kwargs.setdefault("connect_args", {})["timeout"] = 15.0

    eng = create_async_engine(clean_url, **engine_kwargs)
    try:
        # Stage: TLS & Authentication & Connection Handshake
        async with eng.connect() as conn:
            # Stage: SELECT 1
            t0 = time.time()
            select_res = await conn.execute(text("SELECT 1"))
            val = select_res.scalar()
            select_latency = round((time.time() - t0) * 1000, 1)

            # Stage: Alembic Current Revision Check
            version_res = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_name = 'alembic_version'
            """))
            has_alembic_table = version_res.scalar() is not None

            current_revision = None
            is_empty_db = False
            if has_alembic_table:
                rev_res = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                current_revision = rev_res.scalar()
            else:
                is_empty_db = True

            return {
                "connect_success": True,
                "select_success": val == 1,
                "select_latency_ms": select_latency,
                "has_alembic_table": has_alembic_table,
                "current_revision": current_revision,
                "is_empty_db": is_empty_db,
                "error_stage": None,
                "error_type": None,
                "error_message": None,
            }
    except Exception as exc:
        err_str = str(exc)
        err_type = type(exc).__name__

        # Classify exact failure stage and reason without exposing secrets
        stage = "CONNECT"
        classified_type = "CONNECTION_ERROR"
        user_msg = "Database connection failed."

        if "InvalidPasswordError" in err_type or "password authentication failed" in err_str:
            stage = "AUTH"
            classified_type = "AUTHENTICATION_FAILED"
            user_msg = "Password authentication failed for user. Please check your Neon database credentials."
        elif "InvalidCatalogNameError" in err_type or "database" in err_str and "does not exist" in err_str:
            stage = "DATABASE"
            classified_type = "DATABASE_NOT_FOUND"
            user_msg = "Database specified does not exist on target host."
        elif "SSLError" in err_type or "certificate" in err_str.lower() or "ssl" in err_str.lower():
            stage = "TLS"
            classified_type = "TLS_HANDSHAKE_FAILED"
            user_msg = "TLS / SSL handshake failed."
        elif "TimeoutError" in err_type or "timeout" in err_str.lower():
            stage = "TIMEOUT"
            classified_type = "CONNECTION_TIMEOUT"
            user_msg = "Connection attempt timed out. Compute may be suspended or port 5432 unreachable."
        elif "gaierror" in err_type or "getaddrinfo" in err_str.lower():
            stage = "DNS"
            classified_type = "DNS_LOOKUP_FAILED"
            user_msg = "DNS lookup failed for database host."

        return {
            "connect_success": False,
            "select_success": False,
            "select_latency_ms": None,
            "has_alembic_table": False,
            "current_revision": None,
            "is_empty_db": False,
            "error_stage": stage,
            "error_type": classified_type,
            "error_message": user_msg,
            "details": f"{err_type}: {err_str}",
        }
    finally:
        await eng.dispose()


import re

def sanitize_text(text_val: Optional[str], raw_url: Optional[str] = None) -> str:
    """Removes sensitive credentials and masks connection strings."""
    if not text_val:
        return ""
    # Mask postgresql://user:password@ pattern
    sanitized = re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", str(text_val))
    if raw_url:
        try:
            parsed = make_url(raw_url)
            if parsed.password and parsed.password in sanitized:
                sanitized = sanitized.replace(parsed.password, "***")
        except Exception:
            pass
    return sanitized


def run_full_diagnostics(raw_url: str) -> Dict[str, Any]:
    """Runs the complete non-destructive diagnostics pipeline."""
    # Ensure DNS fallback is registered
    ensure_neon_dns_fallback()

    try:
        clean_url, extra_kwargs = prepare_database_url_and_args(raw_url)
        url_obj = make_url(clean_url)
    except Exception as exc:
        return {
            "overall_status": "FAILED",
            "ready_for_migration": False,
            "failing_stage": "input",
            "error_type": "INVALID_DATABASE_URL",
            "error_message": f"Could not parse DATABASE_URL: {sanitize_text(str(exc), raw_url)}",
        }

    host = url_obj.host or ""
    database = url_obj.database or ""
    username = url_obj.username or ""
    is_pooled = "-pooler" in host
    direct_host = host.replace("-pooler", "") if is_pooled else host

    diagnostic_result: Dict[str, Any] = {
        "target_host": host,
        "direct_host": direct_host,
        "target_database": database,
        "target_user": username,
        "is_pooled": is_pooled,
        "driver": url_obj.drivername,
        "stages": {},
        "overall_status": "FAILED",
        "ready_for_migration": False,
    }

    # 1. Target Host Verification
    is_neon = host.endswith(".neon.tech")
    diagnostic_result["stages"]["target_verification"] = {
        "success": is_neon,
        "is_neon": is_neon,
        "message": "Host verified as Neon PostgreSQL" if is_neon else "Host does not end in .neon.tech",
    }
    if not is_neon:
        diagnostic_result["failing_stage"] = "target_verification"
        diagnostic_result["error_message"] = "Host verification failed: target host does not end in .neon.tech"
        return diagnostic_result

    # 2. DNS Check
    dns_info = run_dns_check(host)
    diagnostic_result["stages"]["dns"] = dns_info
    if not dns_info["success"]:
        diagnostic_result["failing_stage"] = "dns"
        diagnostic_result["error_message"] = dns_info["message"]
        return diagnostic_result

    # 3. TCP Port 5432 Check
    target_ip = dns_info["primary_ip"]
    tcp_info = run_tcp_check(target_ip, port=5432, timeout_seconds=5.0)
    diagnostic_result["stages"]["tcp"] = tcp_info
    if not tcp_info["success"]:
        diagnostic_result["failing_stage"] = "tcp"
        diagnostic_result["error_message"] = tcp_info["message"]
        return diagnostic_result

    # 4. Async Database Handshake, SELECT 1, and Alembic Revision
    db_info = asyncio.run(run_async_database_checks(clean_url, extra_kwargs))
    diagnostic_result["stages"]["database"] = db_info

    if not db_info["connect_success"]:
        diagnostic_result["failing_stage"] = db_info["error_stage"]
        diagnostic_result["error_type"] = db_info["error_type"]
        diagnostic_result["error_message"] = db_info["error_message"]
        diagnostic_result["error_details"] = sanitize_text(db_info.get("details"), raw_url)
        return diagnostic_result

    diagnostic_result["stages"]["select_1"] = {
        "success": db_info["select_success"],
        "latency_ms": db_info["select_latency_ms"],
    }

    diagnostic_result["stages"]["alembic"] = {
        "has_alembic_table": db_info["has_alembic_table"],
        "current_revision": db_info["current_revision"],
        "is_empty_db": db_info["is_empty_db"],
    }

    diagnostic_result["overall_status"] = "READY"
    diagnostic_result["ready_for_migration"] = True
    return diagnostic_result


async def run_table_verification_async(clean_url: str, extra_kwargs: dict) -> Dict[str, Any]:
    """Queries information_schema for base tables and checks users and organizations."""
    engine_kwargs = {"echo": False}
    if "connect_args" in extra_kwargs:
        engine_kwargs["connect_args"] = dict(extra_kwargs["connect_args"])

    eng = create_async_engine(clean_url, **engine_kwargs)
    try:
        async with eng.connect() as conn:
            res = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = [r[0] for r in res.fetchall()]
        has_users = "users" in tables
        has_orgs = "organizations" in tables
        return {
            "success": True,
            "count": len(tables),
            "has_users": has_users,
            "has_orgs": has_orgs,
            "tables": tables,
        }
    except Exception as exc:
        return {
            "success": False,
            "count": 0,
            "has_users": False,
            "has_orgs": False,
            "tables": [],
            "error": sanitize_text(str(exc), clean_url),
        }
    finally:
        await eng.dispose()


def run_table_verification(raw_url: str) -> Dict[str, Any]:
    """Synchronous entry point for table verification."""
    ensure_neon_dns_fallback()
    clean_url, extra_kwargs = prepare_database_url_and_args(raw_url)
    return asyncio.run(run_table_verification_async(clean_url, extra_kwargs))


def main():
    import os

    # 1. Help flag
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h", "help"):
        print(json.dumps({
            "name": "AutoHeal Database Diagnostic Suite",
            "description": "Non-destructive pre-flight check for PostgreSQL / Neon connectivity.",
            "usage": "python -m app.db_diagnostic [--verify-tables] [DATABASE_URL]",
            "environment": "Reads DATABASE_URL from environment if not passed as an argument."
        }, indent=2))
        sys.exit(0)

    # 2. Table verification mode
    if "--verify-tables" in sys.argv:
        raw_url = os.environ.get("DATABASE_URL")
        if not raw_url:
            print(json.dumps({"success": False, "count": 0, "has_users": False, "has_orgs": False, "error": "No DATABASE_URL in environment"}))
            sys.exit(1)
        res = run_table_verification(raw_url)
        print(json.dumps(res, indent=2))
        sys.exit(0 if res.get("success") else 1)

    raw_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")

    if not raw_url or not raw_url.strip():
        print(json.dumps({
            "overall_status": "FAILED",
            "ready_for_migration": False,
            "failing_stage": "input",
            "error_type": "MISSING_DATABASE_URL",
            "error_message": "No DATABASE_URL configured or passed to diagnostic runner."
        }, indent=2))
        sys.exit(1)

    result = run_full_diagnostics(raw_url)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ready_for_migration"] else 2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "overall_status": "FAILED",
            "ready_for_migration": False,
            "failing_stage": "startup",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "details": "Fatal unhandled exception during diagnostic runner execution."
        }, indent=2))
        sys.exit(3)
