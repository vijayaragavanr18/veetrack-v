from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Return a configured async session factory."""
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
