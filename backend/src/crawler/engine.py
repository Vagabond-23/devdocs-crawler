"""
Crawl engine — main orchestrator that coordinates the distributed crawl.

The engine:
1. Seeds the frontier with initial URLs
2. Runs the scheduler loop
3. Dispatches URLs to async workers
4. Tracks job progress
5. Handles graceful shutdown

This is the "brain" of the crawler that ties all components together.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select, update

from src.config import settings
from src.crawler.deduplicator import Deduplicator
from src.crawler.frontier import Frontier
from src.crawler.indexer import Indexer
from src.crawler.rate_limiter import RateLimiter
from src.crawler.robots import RobotsManager
from src.crawler.scheduler import Scheduler
from src.crawler.url_normalizer import extract_hostname, normalize_url
from src.crawler.worker import Worker
from src.db.session import async_session_factory
from src.models import CrawlJob, JobStatus

logger = logging.getLogger(__name__)


class CrawlEngine:
    """
    Main crawl engine that orchestrates the distributed crawl.

    Lifecycle:
    1. Initialize components (frontier, scheduler, workers)
    2. Seed the frontier with starting URLs
    3. Run scheduler loop → dispatch to workers → process results
    4. Shut down cleanly
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._frontier = Frontier(redis)
        self._rate_limiter = RateLimiter(redis)
        self._scheduler = Scheduler(redis, self._frontier, self._rate_limiter)
        self._deduplicator = Deduplicator(redis)
        self._indexer = Indexer()
        self._robots = RobotsManager(redis)
        self._running = False
        self._active_tasks: set[asyncio.Task] = set()

    async def run_job(self, job_id: str, seed_urls: list[str]) -> None:
        """
        Run a complete crawl job.

        Args:
            job_id: UUID of the CrawlJob record.
            seed_urls: Initial URLs to crawl.
        """
        self._running = True
        logger.info(f"Starting crawl job {job_id} with {len(seed_urls)} seeds")

        # Update job status
        async with async_session_factory() as db:
            await db.execute(
                update(CrawlJob)
                .where(CrawlJob.id == uuid.UUID(job_id))
                .values(status=JobStatus.RUNNING, started_at=datetime.now(timezone.utc))
            )
            await db.commit()

        # ── Seed the frontier ──
        for url in seed_urls:
            normalized = normalize_url(url)
            if normalized:
                hostname = extract_hostname(normalized)
                if hostname:
                    await self._frontier.enqueue(normalized, hostname)
                    logger.info(f"Seeded: {normalized}")

        # ── Run the scheduler loop ──
        try:
            await self._scheduler_loop(job_id)
        except Exception as e:
            logger.error(f"Crawl engine error: {e}")
        finally:
            await self._shutdown(job_id)

    async def _scheduler_loop(self, job_id: str) -> None:
        """
        Main scheduler loop.

        Continuously asks the scheduler for the next URL and dispatches
        it to a worker. Limits concurrency to max_workers.
        """
        max_workers = settings.crawler_max_workers
        idle_rounds = 0  # Count rounds with no work to detect completion

        while self._running:
            # Clean up finished tasks
            done_tasks = {t for t in self._active_tasks if t.done()}
            self._active_tasks.difference_update(done_tasks)

            for task in done_tasks:
                if task.exception():
                    logger.error(f"Worker error: {task.exception()}")

            # Wait if we're at max concurrency
            if len(self._active_tasks) >= max_workers:
                await asyncio.wait(
                    self._active_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                continue

            # Get next URL from scheduler
            scheduled = await self._scheduler.next_url()

            if scheduled is None:
                # No URLs available right now
                idle_rounds += 1

                # If we have no active tasks and no queued URLs, we're done
                if not self._active_tasks and idle_rounds > 5:
                    logger.info("No more URLs to crawl — job complete")
                    break

                await asyncio.sleep(1)
                continue

            idle_rounds = 0

            # Dispatch to worker
            task = asyncio.create_task(
                self._dispatch_worker(scheduled.url, scheduled.hostname, job_id)
            )
            self._active_tasks.add(task)

        # Wait for remaining tasks
        if self._active_tasks:
            await asyncio.wait(self._active_tasks)

    async def _dispatch_worker(
        self, url: str, hostname: str, job_id: str
    ) -> None:
        """Dispatch a single URL to a worker."""
        await self._scheduler.register_worker(hostname)
        worker = Worker(
            redis=self._redis,
            frontier=self._frontier,
            deduplicator=self._deduplicator,
            indexer=self._indexer,
            robots=self._robots,
            job_id=job_id,
        )
        try:
            await worker.process(url, hostname)
        finally:
            await self._scheduler.release_worker(hostname)
            await worker.close()

    async def _shutdown(self, job_id: str) -> None:
        """Clean up resources and update job status."""
        self._running = False

        # Update job status
        async with async_session_factory() as db:
            await db.execute(
                update(CrawlJob)
                .where(CrawlJob.id == uuid.UUID(job_id))
                .values(
                    status=JobStatus.COMPLETED,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        # Clean up resources
        await self._robots.close()
        await self._indexer.close()

        logger.info(f"Crawl job {job_id} completed")

    async def stop(self) -> None:
        """Gracefully stop the crawl engine."""
        logger.info("Stopping crawl engine...")
        self._running = False
