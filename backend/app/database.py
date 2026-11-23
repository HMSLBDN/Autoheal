"""
AutoHeal DevOps — Database Connection & Async Session Engine
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Optional, Tuple
import logging
import os
import ssl
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def create_database_ssl_context(settings_obj=None) -> Optional[ssl.SSLContext]:
    """
    Constructs an explicit SSLContext for asyncpg when custom CA certificates,
    client certificates, or explicit verify modes are configured.
    """
    cfg = settings_obj or settings
    if not cfg.DB_SSL_CA_CERT and not cfg.DB_SSL_CLIENT_CERT and not cfg.DB_SSL_MODE:
        return None

    mode = cfg.DB_SSL_MODE or "require"
    if mode == "disable":
        return None

    if mode in ("verify-full", "verify-ca"):
        context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=cfg.DB_SSL_CA_CERT,
        )
        if mode == "verify-ca":
            context.check_hostname = False
        else:
            context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
    else:  # require or prefer
        if cfg.DB_SSL_CA_CERT:
            context = ssl.create_default_context(cafile=cfg.DB_SSL_CA_CERT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

    if cfg.DB_SSL_CLIENT_CERT:
        if not os.path.isfile(cfg.DB_SSL_CLIENT_CERT):
            raise FileNotFoundError(f"Configured DB_SSL_CLIENT_CERT not found: {cfg.DB_SSL_CLIENT_CERT}")
        if not cfg.DB_SSL_CLIENT_KEY or not os.path.isfile(cfg.DB_SSL_CLIENT_KEY):
            raise FileNotFoundError(f"Configured DB_SSL_CLIENT_KEY not found or missing: {cfg.DB_SSL_CLIENT_KEY}")
        context.load_cert_chain(cfg.DB_SSL_CLIENT_CERT, cfg.DB_SSL_CLIENT_KEY)

    return context


def get_engine_args(database_url: str) -> dict:
    """
    Returns engine arguments optimized for the target database dialect.
    """
    engine_kwargs: dict = {
        "echo": settings.DEBUG and settings.APP_ENV == "development",
        "future": True,
    }

    if database_url.startswith("sqlite"):
        # SQLite async options (memory or file)
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url:
            engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs["poolclass"] = NullPool
    else:
        # Check for Serverless runtime or explicit NullPool configuration
        is_serverless = (
            os.environ.get("VERCEL") == "1"
            or os.environ.get("AWS_LAMBDA_FUNCTION_NAME") is not None
            or getattr(settings, "DB_POOL_CLASS", None) == "NullPool"
            or os.environ.get("DB_POOL_CLASS") == "NullPool"
            or "-pooler" in database_url
        )

        if is_serverless:
            # NullPool is optimal for serverless environments (e.g. Vercel + Neon pooler)
            # where connections should not persist across ephemeral invocations.
            engine_kwargs["poolclass"] = NullPool
        else:
            # PostgreSQL (asyncpg) pool configuration for persistent workers/servers
            engine_kwargs.update({
                "pool_pre_ping": True,
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_recycle": settings.DB_POOL_RECYCLE,
                "pool_timeout": settings.DB_POOL_TIMEOUT,
            })
        ssl_ctx = create_database_ssl_context(settings)
        if ssl_ctx:
            engine_kwargs.setdefault("connect_args", {})["ssl"] = ssl_ctx

    return engine_kwargs


def validate_database_url(url: str) -> None:
    """
    Validates that the provided DATABASE_URL is non-empty and parsable by SQLAlchemy.
    """
    if not url or not url.strip():
        raise ValueError("DATABASE_URL is not configured. A valid SQLAlchemy connection string is required.")
    try:
        from sqlalchemy.engine import make_url
        parsed = make_url(url)
        if not parsed.drivername or not parsed.drivername.startswith(("postgresql", "sqlite", "postgres")):
            raise ValueError(
                f"DATABASE_URL '{url}' does not specify a supported database driver. "
                "Supported dialects are PostgreSQL and SQLite."
            )
    except Exception as exc:
        raise ValueError(f"Invalid DATABASE_URL configuration '{url}': {exc}") from exc


def prepare_database_url_and_args(raw_url: str) -> Tuple[str, dict]:
    """
    Authoritative helper that prepares a database URL and connection arguments for asyncpg.
    1. Runs Settings.assemble_database_url to normalize protocol and remove libpq unsupported parameters.
    2. For PostgreSQL asyncpg connections, extracts server settings like 'application_name'
       and 'search_path' from the URL query and moves them to connect_args['server_settings'],
       preventing asyncpg.connect() TypeError on unexpected keyword arguments.
    3. Returns (clean_url, extra_engine_kwargs).
    """
    if not raw_url or raw_url.startswith("sqlite"):
        return raw_url, {}

    normalized = settings.assemble_database_url(raw_url) if hasattr(settings, "assemble_database_url") else raw_url
    try:
        url_obj = make_url(normalized)
        query = dict(url_obj.query)
        server_settings: dict = {}

        # application_name and search_path are supported by PostgreSQL server_settings in asyncpg,
        # but NOT as top-level asyncpg.connect() kwargs.
        if "application_name" in query:
            server_settings["application_name"] = query.pop("application_name")
        if "search_path" in query:
            server_settings["search_path"] = query.pop("search_path")

        # Strip any other non-asyncpg keyword arguments that might remain in the query string
        valid_asyncpg_query_keys = {
            "ssl",
            "statement_cache_size",
            "max_cached_statement_lifetime",
            "max_cacheable_statement_size",
            "command_timeout",
            "timeout",
        }
        filtered_query = {k: v for k, v in query.items() if k in valid_asyncpg_query_keys}

        extra_kwargs: dict = {}
        if server_settings:
            extra_kwargs.setdefault("connect_args", {})["server_settings"] = server_settings

        clean_url = url_obj.set(query=filtered_query).render_as_string(hide_password=False)
        return clean_url, extra_kwargs
    except Exception as exc:
        logger.warning("Could not parse/clean database URL '%s': %s", raw_url, exc)
        return normalized, {}


def create_engine_and_session_factory(db_url: Optional[str] = None):
    """
    Factory function creating an AsyncEngine and async_sessionmaker pair.
    Validates the connection URL before instantiation and safely routes server_settings.
    """
    raw_url = db_url or settings.DATABASE_URL
    validate_database_url(raw_url)
    clean_url, extra_kwargs = prepare_database_url_and_args(raw_url)
    engine_args = get_engine_args(clean_url)

    if "connect_args" in extra_kwargs:
        engine_args.setdefault("connect_args", {}).update(extra_kwargs["connect_args"])

    eng = create_async_engine(clean_url, **engine_args)
    factory = async_sessionmaker(
        bind=eng,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    return eng, factory


# Create AsyncEngine singleton and session factory
engine, async_session_factory = create_engine_and_session_factory()
async_engine = engine


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session per request.
    Handles commit on success, automatic rollback on error, and session closure.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("Database session rolled back due to error: %s", exc)
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_isolated_task_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Creates an isolated AsyncSession with NullPool and explicitly disposes the engine on exit.
    Specifically designed for background Celery tasks running in ephemeral event loops.
    """
    clean_url, extra_kwargs = prepare_database_url_and_args(settings.DATABASE_URL)
    engine_kwargs: dict = {
        "poolclass": NullPool,
        "echo": False,
    }
    ssl_ctx = create_database_ssl_context(settings)
    if ssl_ctx:
        engine_kwargs.setdefault("connect_args", {})["ssl"] = ssl_ctx
    if "connect_args" in extra_kwargs:
        engine_kwargs.setdefault("connect_args", {}).update(extra_kwargs["connect_args"])

    task_engine = create_async_engine(
        clean_url,
        **engine_kwargs,
    )
    task_session_factory = async_sessionmaker(
        bind=task_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        async with task_session_factory() as session:
            yield session
    finally:
        await task_engine.dispose()


async def check_database_health() -> Dict[str, str]:
    """
    Safely probes database reachability and schema readiness without raising unhandled exceptions.
    Distinguishes:
    - database: 'connected' | 'unreachable' | 'not_configured'
    - schema: 'ready' | 'pending' | 'error'
    """
    if not settings.DATABASE_URL:
        return {"database": "not_configured", "schema": "not_configured"}

    from sqlalchemy import text
    try:
        async with async_session_factory() as session:
            # 1. Probe connectivity
            await session.execute(text("SELECT 1"))

            # 2. Probe schema readiness (users table must exist)
            schema_status = "pending"
            try:
                await session.execute(text("SELECT id FROM users LIMIT 1"))
                schema_status = "ready"
            except Exception as schema_err:
                logger.warning("Database schema check probe (users table): %s", schema_err)
                schema_status = "pending"

            return {"database": "connected", "schema": schema_status}
    except Exception as db_err:
        logger.warning("Database health check probe failed: %s", db_err)
        return {"database": "unreachable", "schema": "error"}
