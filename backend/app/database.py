"""
AutoHeal DevOps — Database Connection & Async Session Engine
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
import logging
import os
import ssl
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
        # PostgreSQL (asyncpg) pool configuration
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


def create_engine_and_session_factory(db_url: Optional[str] = None):
    """
    Factory function creating an AsyncEngine and async_sessionmaker pair.
    Validates the connection URL before instantiation.
    """
    url = db_url or settings.DATABASE_URL
    validate_database_url(url)
    engine_args = get_engine_args(url)
    eng = create_async_engine(url, **engine_args)
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
    engine_kwargs: dict = {
        "poolclass": NullPool,
        "echo": False,
    }
    ssl_ctx = create_database_ssl_context(settings)
    if ssl_ctx:
        engine_kwargs.setdefault("connect_args", {})["ssl"] = ssl_ctx

    task_engine = create_async_engine(
        settings.DATABASE_URL,
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
