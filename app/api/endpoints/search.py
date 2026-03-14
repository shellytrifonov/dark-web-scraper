"""Dark web search endpoints."""

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.tasks import search_dark_web_task
from app.services.search_engines import get_available_engines

router = APIRouter()


class SearchRequest(BaseModel):
    """Request model for dark web search."""

    query: str
    max_results: int = 50
    scrape_results: bool = False
    timeout: int = 30


class SearchResponse(BaseModel):
    """Response model for search initiation."""

    task_id: str
    query: str
    status: str
    message: str


@router.post("/", response_model=SearchResponse)
async def search_dark_web(request: SearchRequest) -> Dict[str, Any]:
    """
    Search dark web search engines for .onion links matching the query.

    The search is performed asynchronously via Celery. If scrape_results=True,
    discovered URLs will automatically be queued for scraping.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    task = search_dark_web_task.delay(
        query=request.query,
        max_results=request.max_results,
        scrape_results=request.scrape_results,
        timeout=request.timeout,
    )

    return {
        "task_id": task.id,
        "query": request.query,
        "status": "queued",
        "message": f"Dark web search queued for: {request.query}",
    }


@router.get("/engines")
async def list_search_engines() -> List[Dict[str, str]]:
    """List all available dark web search engines."""
    return get_available_engines()
