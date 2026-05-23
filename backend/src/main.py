"""
FastAPI application entry point.

Sets up:
- Lifespan events (startup/shutdown for DB, Redis, Meilisearch)
- CORS middleware
- API routers
- Health check
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.db.session import async_engine
from src.db.base import Base
from src.dependencies import close_redis, close_meili
from src.api import health, search, crawl, stats


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Startup: create database tables (dev convenience — use Alembic in production).
    Shutdown: close connection pools.
    """
    # ── Startup ──
    async with async_engine.begin() as conn:
        # Import models so they're registered with Base.metadata
        import src.models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)

    yield

    # ── Shutdown ──
    await close_redis()
    await close_meili()
    await async_engine.dispose()


app = FastAPI(
    title="DevDocs Crawler API",
    description="Distributed web crawler and search engine for documentation sites",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
app.include_router(search.router, prefix="/api/v1", tags=["Search"])
app.include_router(crawl.router, prefix="/api/v1", tags=["Crawl"])
app.include_router(stats.router, prefix="/api/v1", tags=["Stats"])
