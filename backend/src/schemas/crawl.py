"""Pydantic schemas for crawl management API."""

from datetime import datetime

from pydantic import BaseModel, HttpUrl


class StartCrawlRequest(BaseModel):
    """Request to start a new crawl job."""

    seed_urls: list[str]
    max_depth: int | None = None
    max_pages: int | None = None


class CrawlJobResponse(BaseModel):
    """Response for a crawl job."""

    id: str
    status: str
    seed_urls: list[str]
    pages_crawled: int
    pages_failed: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
