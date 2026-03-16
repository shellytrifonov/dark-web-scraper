"""Site monitoring models for periodic scanning and uptime tracking."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SiteMonitor(Base, TimestampMixin):
    """
    Tracks which URLs are being periodically monitored.

    Each record represents a single URL with its scanning schedule,
    current status, and content versioning metadata.
    """

    __tablename__ = "site_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Scheduling
    frequency_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Latest state
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )  # "up", "down", "timeout"
    last_content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # SHA-256 of html_content

    # Content versioning
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_change_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Uptime stats (rolling)
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<SiteMonitor(id={self.id}, url='{self.url[:50]}...', active={self.is_active})>"

    @property
    def uptime_pct(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return round(self.successful_checks / self.total_checks * 100, 1)


class UptimeRecord(Base):
    """
    Individual check record for uptime tracking.

    One row per monitoring check attempt, used to build the uptime
    timeline bars in the UI.
    """

    __tablename__ = "uptime_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    monitor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Result
    status: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # "up", "down", "timeout", "error"
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Content diff
    content_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size_delta_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<UptimeRecord(id={self.id}, monitor_id={self.monitor_id}, status='{self.status}')>"
