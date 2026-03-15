from datetime import datetime
from typing import Dict, Any, List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.database import get_db
from app.models.scrape_job import ScrapeJob, JobStatus

router = APIRouter()


class JobStatusResponse(BaseModel):
    """Response model for job status."""

    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None


class JobResponse(BaseModel):
    """Response model for job data."""

    id: int
    celery_task_id: Optional[str]
    target_url: str
    status: str
    error_message: Optional[str]
    retries: int
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/status/{task_id}", response_model=JobStatusResponse)
async def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status of a Celery task by its ID.
    
    Returns the current state and result (if completed).
    """
    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.status,
        "result": None,
        "error": None,
    }

    if task_result.successful():
        response["result"] = task_result.result
    elif task_result.failed():
        response["error"] = str(task_result.result)

    return response


@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by job status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> List[ScrapeJob]:
    """List all scrape jobs with optional filtering."""
    query = select(ScrapeJob).order_by(ScrapeJob.created_at.desc())

    if status:
        query = query.where(ScrapeJob.status == status)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str) -> Dict[str, str]:
    """Cancel a pending or running task."""
    celery_app.control.revoke(task_id, terminate=True)
    return {"message": f"Task {task_id} cancellation requested"}


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Delete a job record from the database."""
    result = await db.execute(select(ScrapeJob).where(ScrapeJob.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.delete(job)
    await db.commit()

    return {"message": f"Job {job_id} deleted successfully"}
