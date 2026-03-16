"""Site Pulse – monitoring endpoints for periodic scanning and uptime tracking."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.site_monitor import SiteMonitor, UptimeRecord
from app.services.tasks import monitor_site_task

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class MonitorCreate(BaseModel):
    url: str
    label: Optional[str] = None
    frequency_hours: int = 6


class MonitorUpdate(BaseModel):
    label: Optional[str] = None
    frequency_hours: Optional[int] = None
    is_active: Optional[bool] = None


class MonitorResponse(BaseModel):
    id: int
    url: str
    label: Optional[str]
    frequency_hours: int
    is_active: bool
    last_checked_at: Optional[datetime]
    last_status: Optional[str]
    version_count: int
    last_change_at: Optional[datetime]
    last_change_summary: Optional[str]
    total_checks: int
    successful_checks: int
    uptime_pct: float
    created_at: datetime

    class Config:
        from_attributes = True


class UptimeRecordResponse(BaseModel):
    id: int
    monitor_id: int
    checked_at: datetime
    status: str
    status_code: Optional[int]
    response_time_ms: Optional[int]
    error_message: Optional[str]
    content_changed: bool
    change_summary: Optional[str]
    size_delta_bytes: Optional[int]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[MonitorResponse])
async def list_monitors(
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(False),
) -> List[Any]:
    """List all site monitors."""
    query = select(SiteMonitor).order_by(desc(SiteMonitor.created_at))
    if active_only:
        query = query.where(SiteMonitor.is_active == True)
    result = await db.execute(query)
    monitors = result.scalars().all()

    # Attach computed uptime_pct
    out = []
    for m in monitors:
        data = MonitorResponse.model_validate(m)
        data.uptime_pct = m.uptime_pct
        out.append(data)
    return out


@router.post("/", response_model=MonitorResponse)
async def create_monitor(
    body: MonitorCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Add a new URL to monitor."""
    # Check for duplicate
    existing = await db.execute(
        select(SiteMonitor).where(SiteMonitor.url == body.url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="URL is already being monitored")

    monitor = SiteMonitor(
        url=body.url,
        label=body.label,
        frequency_hours=body.frequency_hours,
        is_active=True,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)

    resp = MonitorResponse.model_validate(monitor)
    resp.uptime_pct = 0.0
    return resp


@router.patch("/{monitor_id}", response_model=MonitorResponse)
async def update_monitor(
    monitor_id: int,
    body: MonitorUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update a monitor's settings."""
    result = await db.execute(
        select(SiteMonitor).where(SiteMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    if body.label is not None:
        monitor.label = body.label
    if body.frequency_hours is not None:
        monitor.frequency_hours = body.frequency_hours
    if body.is_active is not None:
        monitor.is_active = body.is_active

    await db.commit()
    await db.refresh(monitor)

    resp = MonitorResponse.model_validate(monitor)
    resp.uptime_pct = monitor.uptime_pct
    return resp


@router.delete("/{monitor_id}")
async def delete_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Remove a monitor."""
    result = await db.execute(
        select(SiteMonitor).where(SiteMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    await db.delete(monitor)
    await db.commit()
    return {"status": "deleted"}


@router.post("/{monitor_id}/check")
async def trigger_check(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Manually trigger an immediate check for a monitor."""
    result = await db.execute(
        select(SiteMonitor).where(SiteMonitor.id == monitor_id)
    )
    monitor = result.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    task = monitor_site_task.delay(
        monitor_id=monitor.id,
        url=monitor.url,
    )
    return {"task_id": task.id, "monitor_id": monitor.id, "url": monitor.url}


# ---------------------------------------------------------------------------
# Uptime timeline
# ---------------------------------------------------------------------------

@router.get("/{monitor_id}/uptime", response_model=List[UptimeRecordResponse])
async def get_uptime_history(
    monitor_id: int,
    hours: int = Query(168, ge=1, le=720, description="Hours of history (default 7 days)"),
    db: AsyncSession = Depends(get_db),
) -> List[Any]:
    """Get uptime records for a monitor within the given time window."""
    since = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(UptimeRecord)
        .where(UptimeRecord.monitor_id == monitor_id)
        .where(UptimeRecord.checked_at >= since)
        .order_by(UptimeRecord.checked_at.asc())
    )
    return result.scalars().all()
