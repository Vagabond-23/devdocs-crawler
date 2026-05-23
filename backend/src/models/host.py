"""
Host model — represents a crawlable documentation domain.

Stores per-host configuration including robots.txt cache, crawl delay,
and concurrency limits. This is the foundation for host-aware scheduling.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Cached robots.txt content — avoids re-fetching on every request.
    robots_txt: Mapped[str | None] = mapped_column(Text, nullable=True)
    robots_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Per-host politeness settings (can be overridden by robots.txt Crawl-delay).
    crawl_delay_ms: Mapped[int] = mapped_column(Integer, default=1000)
    concurrent_limit: Mapped[int] = mapped_column(Integer, default=2)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    pages: Mapped[list["Page"]] = relationship(back_populates="host")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Host {self.hostname}>"
