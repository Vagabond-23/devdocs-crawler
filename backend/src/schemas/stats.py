"""Pydantic schemas for stats/metrics API."""

from pydantic import BaseModel


class SystemStats(BaseModel):
    """Real-time crawler statistics."""

    pages_fetched: int
    pages_failed: int
    pages_not_modified: int
    pages_duplicate: int
    pages_indexed: int
    urls_discovered: int
    active_hosts: int
    active_workers: int
