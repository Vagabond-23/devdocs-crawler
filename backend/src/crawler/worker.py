"""
Async crawl worker — fetches, parses, deduplicates, and indexes pages.

Each worker handles a single URL through the complete pipeline:
1. Conditional HTTP fetch (ETag / Last-Modified)
2. HTML parsing and content extraction
3. Content fingerprinting and dedup
4. PostgreSQL storage
5. Meilisearch indexing
6. Link discovery and frontier enqueue

Workers are stateless and share state via Redis and PostgreSQL.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.crawler.deduplicator import Deduplicator
from src.crawler.frontier import Frontier
from src.crawler.indexer import Indexer
from src.crawler.parser import extract_content, extract_links, extract_title
from src.crawler.robots import RobotsManager
from src.crawler.url_normalizer import extract_hostname, normalize_url
from src.db.session import async_session_factory
from src.models import CrawlEvent, CrawlState, Fingerprint, Host, Link, Page

logger = logging.getLogger(__name__)


class Worker:
    """
    Async fetch worker for the crawl pipeline.

    Processes a single URL end-to-end and reports results back
    to the scheduler via Redis metrics.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        frontier: Frontier,
        deduplicator: Deduplicator,
        indexer: Indexer,
        robots: RobotsManager,
        job_id: str | None = None,
    ) -> None:
        self._redis = redis
        self._frontier = frontier
        self._dedup = deduplicator
        self._indexer = indexer
        self._robots = robots
        self._job_id = job_id
        self._http = httpx.AsyncClient(
            timeout=settings.crawler_request_timeout,
            headers={"User-Agent": settings.crawler_user_agent},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def process(self, url: str, hostname: str) -> None:
        """
        Process a single URL through the full crawl pipeline.

        This is the main entry point called by the scheduler for each URL.
        """
        start_time = time.monotonic()

        async with async_session_factory() as db:
            try:
                # ── 1. Get or create page record ──
                page = await self._get_or_create_page(db, url, hostname)

                # ── 2. Check robots.txt ──
                if not await self._robots.is_allowed(url, hostname):
                    logger.info(f"Blocked by robots.txt: {url}")
                    page.crawl_state = CrawlState.FAILED
                    page.error_message = "Blocked by robots.txt"
                    await db.commit()
                    return

                # ── 3. Update state: DISCOVERED → FETCHING ──
                page.crawl_state = CrawlState.FETCHING
                await db.commit()

                # ── 4. Fetch with conditional headers ──
                headers = {}
                if page.etag:
                    headers["If-None-Match"] = page.etag
                if page.last_modified:
                    headers["If-Modified-Since"] = page.last_modified

                response = await self._http.get(url, headers=headers)
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # ── 5. Handle 304 Not Modified ──
                if response.status_code == 304:
                    page.crawl_state = CrawlState.COMPLETED
                    page.last_crawled_at = datetime.now(timezone.utc)
                    await self._log_event(db, page.id, "304_skip", 304, duration_ms)
                    await self._redis.incr("metrics:pages_304")
                    await db.commit()
                    logger.debug(f"304 Not Modified: {url}")
                    return

                # ── 6. Handle errors ──
                if response.status_code >= 400:
                    await self._handle_error(
                        db, page, response.status_code, duration_ms,
                        f"HTTP {response.status_code}",
                    )
                    return

                # ── 7. Update state: FETCHING → FETCHED ──
                page.crawl_state = CrawlState.FETCHED
                page.status_code = response.status_code
                page.content_type = response.headers.get("content-type", "")
                page.etag = response.headers.get("etag")
                page.last_modified = response.headers.get("last-modified")
                page.last_crawled_at = datetime.now(timezone.utc)
                await self._log_event(db, page.id, "fetch", response.status_code, duration_ms)
                await db.commit()

                # Only process HTML
                content_type = page.content_type or ""
                if "text/html" not in content_type:
                    page.crawl_state = CrawlState.COMPLETED
                    await db.commit()
                    return

                html = response.text

                # ── 8. Parse content ──
                title = extract_title(html)
                content = extract_content(html)
                links = extract_links(html, base_url=url)

                page.title = title[:1024] if title else None
                page.crawl_state = CrawlState.PARSED
                await self._log_event(db, page.id, "parse", None, None)
                await db.commit()

                # ── 9. Deduplication ──
                is_dup, sha256, simhash = await self._dedup.is_duplicate(content)
                if is_dup:
                    page.crawl_state = CrawlState.COMPLETED
                    page.error_message = "Duplicate content"
                    await self._redis.incr("metrics:pages_duplicate")
                    await db.commit()
                    logger.debug(f"Duplicate: {url}")
                    # Still enqueue links from duplicates
                    await self._enqueue_links(links, hostname, page)
                    return

                # Store fingerprint
                fp = Fingerprint(
                    page_id=page.id,
                    sha256=sha256,
                    simhash=str(simhash),
                )
                db.add(fp)
                await self._dedup.register(sha256, simhash)

                # ── 10. Index in Meilisearch ──
                await self._indexer.index_document(
                    doc_id=str(page.id),
                    title=title,
                    content=content,
                    url=url,
                    hostname=hostname,
                )
                page.crawl_state = CrawlState.INDEXED
                await self._log_event(db, page.id, "index", None, None)
                await self._redis.incr("metrics:pages_indexed")

                # ── 11. Update state: INDEXED → COMPLETED ──
                page.crawl_state = CrawlState.COMPLETED
                await self._redis.incr("metrics:pages_fetched")
                await db.commit()

                # ── 12. Enqueue discovered links ──
                await self._enqueue_links(links, hostname, page)

                logger.info(f"✓ {url} ({duration_ms}ms, {len(links)} links)")

            except httpx.TimeoutException:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                page = await self._get_page(db, url)
                if page:
                    await self._handle_error(db, page, None, duration_ms, "Timeout")
                logger.warning(f"Timeout: {url}")

            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                page = await self._get_page(db, url)
                if page:
                    await self._handle_error(db, page, None, duration_ms, str(e))
                logger.error(f"Error processing {url}: {e}")

    async def _get_or_create_page(
        self, db: AsyncSession, url: str, hostname: str
    ) -> Page:
        """Get existing page record or create a new one."""
        result = await db.execute(select(Page).where(Page.url == url))
        page = result.scalar_one_or_none()

        if page is None:
            # Ensure host record exists
            host = await self._get_or_create_host(db, hostname)

            page = Page(
                url=url,
                canonical_url=url,
                host_id=host.id,
                crawl_state=CrawlState.DISCOVERED,
            )
            db.add(page)
            await db.flush()

        return page

    async def _get_page(self, db: AsyncSession, url: str) -> Page | None:
        """Get page by URL."""
        result = await db.execute(select(Page).where(Page.url == url))
        return result.scalar_one_or_none()

    async def _get_or_create_host(
        self, db: AsyncSession, hostname: str
    ) -> Host:
        """Get existing host record or create a new one."""
        result = await db.execute(select(Host).where(Host.hostname == hostname))
        host = result.scalar_one_or_none()

        if host is None:
            host = Host(
                hostname=hostname,
                crawl_delay_ms=settings.crawler_default_delay_ms,
            )
            db.add(host)
            await db.flush()

        return host

    async def _handle_error(
        self,
        db: AsyncSession,
        page: Page,
        status_code: int | None,
        duration_ms: int,
        error_msg: str,
    ) -> None:
        """Handle fetch errors with retry logic."""
        page.retry_count += 1
        page.error_message = error_msg

        if page.retry_count < settings.crawler_max_retries:
            # Re-enqueue with exponential backoff
            page.crawl_state = CrawlState.DISCOVERED
            backoff = 5 ** page.retry_count
            await asyncio.sleep(min(backoff, 120))
            await self._frontier.enqueue(page.url, extract_hostname(page.url))
        else:
            page.crawl_state = CrawlState.FAILED
            await self._redis.incr("metrics:pages_failed")

        await self._log_event(db, page.id, "error", status_code, duration_ms, error_msg)
        await db.commit()

    async def _enqueue_links(
        self,
        links: list[dict[str, str]],
        source_hostname: str,
        source_page: Page,
    ) -> None:
        """Enqueue discovered links that pass the allowlist filter."""
        allowed = settings.allowed_hosts_list

        for link_data in links:
            raw_url = link_data["url"]
            normalized = normalize_url(raw_url)
            if normalized is None:
                continue

            link_host = extract_hostname(normalized)
            if link_host is None or link_host not in allowed:
                continue

            # Check depth limit
            new_depth = source_page.depth + 1
            if new_depth > settings.crawler_max_depth:
                continue

            await self._frontier.enqueue(normalized, link_host)

    async def _log_event(
        self,
        db: AsyncSession,
        page_id: uuid.UUID,
        event_type: str,
        status_code: int | None,
        duration_ms: int | None,
        error: str | None = None,
    ) -> None:
        """Log a crawl event to the audit table."""
        event = CrawlEvent(
            page_id=page_id,
            job_id=uuid.UUID(self._job_id) if self._job_id else None,
            event_type=event_type,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error,
        )
        db.add(event)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()
