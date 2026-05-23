"""Crawl management API — start, stop, and monitor crawl jobs."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db
from src.dependencies import get_redis
from src.models import CrawlJob, JobStatus
from src.schemas.crawl import CrawlJobResponse, StartCrawlRequest
from src.config import settings

router = APIRouter()


@router.post("/crawl/start", response_model=CrawlJobResponse)
async def start_crawl(
    request: StartCrawlRequest,
    db: AsyncSession = Depends(get_db),
) -> CrawlJobResponse:
    """
    Start a new crawl job with the given seed URLs.

    Seeds are validated against the allowlist before being accepted.
    """
    from urllib.parse import urlparse

    allowed = settings.allowed_hosts_list
    validated_seeds = []
    for url in request.seed_urls:
        host = urlparse(url).hostname
        if host in allowed:
            validated_seeds.append(url)

    if not validated_seeds:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"No seed URLs matched allowed hosts: {allowed}",
        )

    job = CrawlJob(
        seed_urls=validated_seeds,
        status=JobStatus.PENDING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    # Trigger crawler in background (non-blocking).
    # The actual crawl engine will pick up the job from the database.
    from src.crawler.engine import CrawlEngine
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    engine = CrawlEngine(redis=redis)
    asyncio.create_task(engine.run_job(str(job.id), validated_seeds))

    return CrawlJobResponse(
        id=str(job.id),
        status=job.status.value,
        seed_urls=validated_seeds,
        pages_crawled=0,
        pages_failed=0,
        started_at=job.started_at,
    )


@router.get("/crawl/jobs", response_model=list[CrawlJobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
) -> list[CrawlJobResponse]:
    """List all crawl jobs, most recent first."""
    result = await db.execute(
        select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(50)
    )
    jobs = result.scalars().all()
    return [
        CrawlJobResponse(
            id=str(j.id),
            status=j.status.value,
            seed_urls=j.seed_urls if isinstance(j.seed_urls, list) else [],
            pages_crawled=j.pages_crawled,
            pages_failed=j.pages_failed,
            started_at=j.started_at,
            finished_at=j.finished_at,
        )
        for j in jobs
    ]


@router.get("/crawl/jobs/{job_id}", response_model=CrawlJobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> CrawlJobResponse:
    """Get details of a specific crawl job."""
    from fastapi import HTTPException
    import uuid

    result = await db.execute(
        select(CrawlJob).where(CrawlJob.id == uuid.UUID(job_id))
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return CrawlJobResponse(
        id=str(job.id),
        status=job.status.value,
        seed_urls=job.seed_urls if isinstance(job.seed_urls, list) else [],
        pages_crawled=job.pages_crawled,
        pages_failed=job.pages_failed,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
