"""
Link model — web graph edges between pages.

Stores the directed link relationship (source → target) along with
anchor text. Enables link analysis and re-crawl prioritization.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id"), nullable=False, index=True
    )
    target_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id"), nullable=True, index=True
    )

    # Anchor text of the link (useful for search relevance).
    anchor_text: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # When we discovered this link
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    source_page: Mapped["Page"] = relationship(  # noqa: F821
        back_populates="outgoing_links", foreign_keys=[source_page_id]
    )

    def __repr__(self) -> str:
        return f"<Link {self.source_page_id} → {self.target_page_id}>"
