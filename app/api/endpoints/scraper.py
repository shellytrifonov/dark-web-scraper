from typing import Dict, Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.scraped_site import ScrapedSite
from app.models.scrape_job import ScrapeJob, JobStatus
from app.services.tasks import scrape_url_task, bulk_scrape_task

router = APIRouter()


class ScrapeRequest(BaseModel):
    """Request model for initiating a scrape."""

    url: str
    use_tor: bool = True
    timeout: int = 30
    force_engine: Literal["auto", "bs4", "selenium"] = "auto"


class ScrapeResponse(BaseModel):
    """Response model for scrape initiation."""

    task_id: str
    status: str
    message: str
    engine: str


class ScrapedSiteResponse(BaseModel):
    """Response model for scraped site data."""

    id: int
    url: str
    title: Optional[str]
    content: Optional[str]
    status_code: Optional[int]
    scraped_at: str

    class Config:
        from_attributes = True


@router.post("/scrape", response_model=ScrapeResponse)
async def initiate_scrape(request: ScrapeRequest) -> Dict[str, Any]:
    """
    Initiate a new scraping task.

    **Smart Scraping Strategy:**
    - `auto` (default): Tries BS4 first (fast, lightweight). If the page
      requires JavaScript, automatically escalates to Selenium.
    - `bs4`: Force BS4 only — fastest, but no JS rendering.
    - `selenium`: Force Selenium only — full browser with JS support.
    """
    task = scrape_url_task.delay(
        url=request.url,
        use_tor=request.use_tor,
        timeout=request.timeout,
        force_engine=request.force_engine,
    )

    return {
        "task_id": task.id,
        "status": "queued",
        "message": f"Scraping task queued for URL: {request.url}",
        "engine": request.force_engine,
    }


@router.get("/results", response_model=List[ScrapedSiteResponse])
async def get_scraped_results(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search in URL or content"),
) -> List[ScrapedSite]:
    """Get all scraped site results with pagination."""
    query = select(ScrapedSite).order_by(ScrapedSite.scraped_at.desc())

    if search:
        query = query.where(
            ScrapedSite.url.ilike(f"%{search}%")
            | ScrapedSite.content.ilike(f"%{search}%")
            | ScrapedSite.title.ilike(f"%{search}%")
        )

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/results/{site_id}", response_model=ScrapedSiteResponse)
async def get_scraped_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
) -> ScrapedSite:
    """Get a specific scraped site by ID."""
    result = await db.execute(
        select(ScrapedSite).where(ScrapedSite.id == site_id)
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Scraped site not found")

    return site


class BulkScrapeRequest(BaseModel):
    """Request model for bulk scraping."""

    urls: List[str]
    use_tor: bool = True
    timeout: int = 30
    force_engine: Literal["auto", "bs4", "selenium"] = "auto"


class BulkScrapeResponse(BaseModel):
    """Response model for bulk scrape initiation."""

    parent_task_id: str
    total_urls: int
    status: str
    message: str


@router.post("/bulk", response_model=BulkScrapeResponse)
async def initiate_bulk_scrape(request: BulkScrapeRequest) -> Dict[str, Any]:
    """
    Initiate bulk scraping for multiple URLs.

    Each URL is processed as an individual Celery task.
    Returns a parent task_id to track the batch.
    """
    if not request.urls:
        raise HTTPException(status_code=400, detail="URL list cannot be empty")

    task = bulk_scrape_task.delay(
        urls=request.urls,
        use_tor=request.use_tor,
        timeout=request.timeout,
        force_engine=request.force_engine,
    )

    return {
        "parent_task_id": task.id,
        "total_urls": len(request.urls),
        "status": "queued",
        "message": f"Bulk scraping queued for {len(request.urls)} URLs",
    }


@router.get("/stats")
async def get_scraper_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Get comprehensive scraper statistics."""
    total_sites_result = await db.execute(select(func.count(ScrapedSite.id)))
    total_sites = total_sites_result.scalar() or 0

    total_jobs_result = await db.execute(select(func.count(ScrapeJob.id)))
    total_jobs = total_jobs_result.scalar() or 0

    pending_result = await db.execute(
        select(func.count(ScrapeJob.id)).where(ScrapeJob.status == JobStatus.PENDING.value)
    )
    pending_jobs = pending_result.scalar() or 0

    running_result = await db.execute(
        select(func.count(ScrapeJob.id)).where(ScrapeJob.status == JobStatus.RUNNING.value)
    )
    running_jobs = running_result.scalar() or 0

    completed_result = await db.execute(
        select(func.count(ScrapeJob.id)).where(ScrapeJob.status == JobStatus.COMPLETED.value)
    )
    completed_jobs = completed_result.scalar() or 0

    failed_result = await db.execute(
        select(func.count(ScrapeJob.id)).where(ScrapeJob.status == JobStatus.FAILED.value)
    )
    failed_jobs = failed_result.scalar() or 0

    return {
        "total_scraped_sites": total_sites,
        "jobs": {
            "total": total_jobs,
            "pending": pending_jobs,
            "running": running_jobs,
            "completed": completed_jobs,
            "failed": failed_jobs,
        },
    }


@router.delete("/results/{site_id}")
async def delete_scraped_site(
    site_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, str]:
    """Delete a scraped site record."""
    result = await db.execute(
        select(ScrapedSite).where(ScrapedSite.id == site_id)
    )
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Scraped site not found")

    await db.delete(site)
    await db.commit()

    return {"message": f"Scraped site {site_id} deleted successfully"}
