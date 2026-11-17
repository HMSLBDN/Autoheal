"""
AutoHeal DevOps — Database Connection & Async Session Engine
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import logging
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

    return engine_kwargs


# Create AsyncEngine singleton
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **get_engine_args(settings.DATABASE_URL),
)

# Async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


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
    task_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=False,
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
