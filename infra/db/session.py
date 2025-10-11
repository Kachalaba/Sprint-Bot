"""Async SQLAlchemy engine and session helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(database_url: str) -> AsyncEngine:
    """Create async SQLAlchemy engine for the provided database URL."""

    return create_async_engine(database_url, pool_pre_ping=True, future=True)


def async_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build async session factory bound to the engine."""

    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
