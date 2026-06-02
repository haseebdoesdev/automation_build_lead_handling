from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

engine = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    pass


def init_db(database_url: str) -> None:
    global engine, async_session_factory
    engine = create_async_engine(database_url, echo=False, pool_size=10, max_overflow=20)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    async with async_session_factory() as session:
        yield session


async def create_tables() -> None:
    if engine is None:
        raise RuntimeError("Database not initialized.")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
