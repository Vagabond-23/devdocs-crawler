"""
CrawlJob model — groups pages into logical crawl runs.

Enables starting, stopping, and resuming crawl sessions.
Tracks aggregate progress (pages crawled, failed).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)

    # Seed URLs that initiated this crawl job.
    seed_urls: Mapped[dict] = mapped_column(JSONB, default=list)

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Aggregate counters — updated as crawl progresses.
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    events: Mapped[list["CrawlEvent"]] = relationship(back_populates="job")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CrawlJob {self.id} [{self.status.value}]>"
