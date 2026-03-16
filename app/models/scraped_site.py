from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ScrapedSite(Base, TimestampMixin):
    """Model for storing scraped site data."""

    __tablename__ = "scraped_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    html_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Scrape metadata
    engine_used: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    escalated: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=False)
    content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    html_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    links_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    links: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    meta_description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Entity extraction & analysis results (structured JSON)
    entities: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ScrapedSite(id={self.id}, url='{self.url[:50]}...')>"
