"""
Models package — re-exports all ORM models.

Import from here to ensure all models are registered with SQLAlchemy's
metadata before Alembic autogenerate runs.
"""

from src.models.crawl_event import CrawlEvent
from src.models.crawl_job import CrawlJob, JobStatus
from src.models.fingerprint import Fingerprint
from src.models.host import Host
from src.models.link import Link
from src.models.page import CrawlState, Page

__all__ = [
    "CrawlEvent",
    "CrawlJob",
    "CrawlState",
    "Fingerprint",
    "Host",
    "JobStatus",
    "Link",
    "Page",
]
