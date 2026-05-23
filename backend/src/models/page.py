"""
Page model — core entity representing a crawled web page.

Tracks the full lifecycle of a page: discovery → fetch → parse → index.
Stores conditional fetch headers (ETag, Last-Modified) for incremental crawling.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class CrawlState(str, enum.Enum):
    """
    Page lifecycle state machine.

    DISCOVERED → FETCHING → FETCHED → PARSED → INDEXED → COMPLETED
                   ↓           ↓        ↓         ↓
                 FAILED      FAILED   FAILED    FAILED
    """

    DISCOVERED = "discovered"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSED = "parsed"
    INDEXED = "indexed"
    COMPLETED = "completed"
    FAILED = "failed"


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hosts.id"), nullable=False, index=True
    )

    # URL tracking
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Crawl depth from seed URL (0 = seed)
    depth: Mapped[int] = mapped_column(Integer, default=0)

    # State machine
    crawl_state: Mapped[CrawlState] = mapped_column(
        Enum(CrawlState), default=CrawlState.DISCOVERED, index=True
    )

    # Conditional fetch headers — stored after each successful fetch.
    # Sent as If-None-Match / If-Modified-Since on subsequent crawls.
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Response metadata
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    host: Mapped["Host"] = relationship(back_populates="pages")  # noqa: F821
    fingerprint: Mapped["Fingerprint | None"] = relationship(  # noqa: F821
        back_populates="page", uselist=False
    )
    crawl_events: Mapped[list["CrawlEvent"]] = relationship(back_populates="page")  # noqa: F821
    outgoing_links: Mapped[list["Link"]] = relationship(  # noqa: F821
        back_populates="source_page", foreign_keys="Link.source_page_id"
    )

    def __repr__(self) -> str:
        return f"<Page {self.url} [{self.crawl_state.value}]>"
