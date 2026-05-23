"""
Async SQLAlchemy session factory.

Uses asyncpg as the async PostgreSQL driver. Provides:
- async_engine: for running migrations and raw queries
- async_session_factory: for creating scoped sessions
- get_db: FastAPI dependency for request-scoped sessions
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import settings

# Create async engine with connection pooling.
# pool_size=20 handles concurrent crawl workers + API requests.
# max_overflow=10 allows burst capacity.
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,  # Verify connections aren't stale
)

# Session factory — creates new AsyncSession instances.
async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Prevent lazy-load issues in async context
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
