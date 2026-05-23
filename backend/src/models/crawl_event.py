"""
CrawlEvent model — append-only audit log for every fetch attempt.

Every HTTP request the crawler makes is logged here. This enables:
- Debugging failed crawls
- Computing metrics (success rate, latency percentiles)
- Auditing crawler behavior over time
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class CrawlEvent(Base):
    __tablename__ = "crawl_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crawl_jobs.id"), nullable=True, index=True
    )

    # What happened
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g., "fetch", "304_skip", "parse", "index", "error"

    # HTTP response details
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error details (if any)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    page: Mapped["Page"] = relationship(back_populates="crawl_events")  # noqa: F821
    job: Mapped["CrawlJob | None"] = relationship(back_populates="events")  # noqa: F821

    def __repr__(self) -> str:
        return f"<CrawlEvent {self.event_type} page={self.page_id}>"
