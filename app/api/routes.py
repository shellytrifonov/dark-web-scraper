from fastapi import APIRouter

from app.api.endpoints import health, scraper, jobs, config, search, monitor

router = APIRouter()

router.include_router(health.router, prefix="/health", tags=["Health"])
router.include_router(scraper.router, prefix="/scraper", tags=["Scraper"])
router.include_router(search.router, prefix="/search", tags=["Search"])
router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
router.include_router(config.router, prefix="/config", tags=["Configuration"])
router.include_router(monitor.router, prefix="/monitor", tags=["Monitor"])
