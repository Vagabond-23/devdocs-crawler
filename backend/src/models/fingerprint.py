"""
Fingerprint model — content deduplication via SHA-256 and SimHash.

SHA-256 catches exact duplicates (same content, different URL).
SimHash catches near-duplicates (minor template changes, footers, etc.).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import Base


class Fingerprint(Base):
    __tablename__ = "fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id"), nullable=False, unique=True
    )

    # Exact duplicate detection — SHA-256 of cleaned text content.
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Near-duplicate detection — 64-bit SimHash of content tokens.
    # Two documents are near-duplicates if hamming_distance(a, b) <= 3.
    simhash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    page: Mapped["Page"] = relationship(back_populates="fingerprint")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Fingerprint sha256={self.sha256[:12]}... page={self.page_id}>"
