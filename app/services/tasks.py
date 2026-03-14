import logging
from datetime import datetime
from typing import Any, Dict, Optional

from celery import shared_task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.scraped_site import ScrapedSite
from app.models.scrape_job import ScrapeJob, JobStatus
from app.services.selenium_scraper import (
    SeleniumScraper,
    IPLeakError,
    AnonymityVerificationError,
)
from app.services.smart_scraper import SmartScraper, ScrapeEngine
from app.services.search_engines import search_dark_web, SEARCH_ENGINES

logger = logging.getLogger(__name__)

SYNC_DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=sync_engine)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_url_task(
    self,
    url: str,
    use_tor: bool = True,
    timeout: int = 30,
    force_engine: str = "auto",
) -> Dict[str, Any]:
    """
    Celery task to scrape a URL using the smart scraping strategy.

    Args:
        url: Target URL to scrape
        use_tor: Whether to route through Tor proxy
        timeout: Request timeout in seconds
        force_engine: "auto" (BS4 first, escalate if needed), "bs4", or "selenium"

    Returns:
        Dictionary with scraping results
    """
    task_id = self.request.id
    logger.info(f"Starting scrape task {task_id} for URL: {url} (engine={force_engine})")

    # Resolve engine enum
    try:
        engine = ScrapeEngine(force_engine)
    except ValueError:
        engine = ScrapeEngine(settings.DEFAULT_SCRAPE_ENGINE)

    session = SyncSession()

    try:
        job = ScrapeJob(
            celery_task_id=task_id,
            target_url=url,
            status=JobStatus.RUNNING.value,
            started_at=datetime.utcnow(),
        )
        session.add(job)
        session.commit()

        scraper = SmartScraper(
            selenium_hub_url=settings.SELENIUM_HUB_URL,
            tor_host=settings.TOR_PROXY_HOST,
            tor_port=settings.TOR_HTTP_PORT,
            timeout=timeout,
            use_tor=use_tor,
            blacklisted_ips=settings.BLACKLISTED_IPS,
            require_tor_exit_node=settings.REQUIRE_TOR_EXIT_NODE,
            min_content_length=settings.BS4_MIN_CONTENT_LENGTH,
        )

        result = scraper.scrape(url, engine=engine)

        scraped_site = ScrapedSite(
            url=url,
            title=result.get("title"),
            content=result.get("clean_content") or result.get("content"),
            html_content=result.get("html"),
            status_code=result.get("status_code"),
            scraped_at=datetime.utcnow(),
        )
        session.add(scraped_site)

        job.status = JobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
        session.commit()

        logger.info(f"Scrape task {task_id} completed via {result.get('engine_used')}")

        return {
            "success": True,
            "url": url,
            "title": result.get("title"),
            "content_length": len(result.get("content", "")),
            "scraped_site_id": scraped_site.id,
            "engine_used": result.get("engine_used"),
            "escalated": result.get("escalated", False),
        }

    except (IPLeakError, AnonymityVerificationError) as e:
        # CRITICAL: Do NOT retry on IP leak or anonymity failures
        logger.critical(f"Scrape task {task_id} ABORTED due to security violation: {str(e)}")

        try:
            job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = f"SECURITY ABORT: {str(e)}"
                job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass

        return {
            "success": False,
            "url": url,
            "error": str(e),
            "security_abort": True,
        }

    except Exception as e:
        logger.error(f"Scrape task {task_id} failed: {str(e)}")

        try:
            job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)
                job.retries = self.request.retries
                job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {
            "success": False,
            "url": url,
            "error": str(e),
        }

    finally:
        session.close()


@shared_task
def check_scraper_status() -> Dict[str, Any]:
    """
    Periodic task to check the status of scraper infrastructure.
    
    Runs every minute via Celery Beat.
    """
    import httpx

    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "selenium": "unknown",
        "tor": "unknown",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{settings.SELENIUM_HUB_URL}/status")
            if response.status_code == 200:
                data = response.json()
                status["selenium"] = "ready" if data.get("value", {}).get("ready") else "not_ready"
            else:
                status["selenium"] = "error"
    except Exception as e:
        status["selenium"] = f"error: {str(e)}"

    try:
        proxy_url = f"http://{settings.TOR_PROXY_HOST}:{settings.TOR_HTTP_PORT}"
        with httpx.Client(
            proxy=proxy_url,
            timeout=15.0,
        ) as client:
            response = client.get("https://check.torproject.org/api/ip")
            if response.status_code == 200:
                data = response.json()
                status["tor"] = "connected" if data.get("IsTor") else "not_tor"
                status["tor_ip"] = data.get("IP")
            else:
                status["tor"] = "error"
    except Exception as e:
        status["tor"] = f"error: {str(e)}"

    logger.info(f"Scraper status check: {status}")
    return status


@shared_task(bind=True)
def bulk_scrape_task(
    self,
    urls: list,
    use_tor: bool = True,
    timeout: int = 30,
    force_engine: str = "auto",
) -> Dict[str, Any]:
    """
    Celery task to scrape multiple URLs.
    
    Creates individual tasks for each URL.
    """
    task_ids = []
    for url in urls:
        task = scrape_url_task.delay(
            url=url, use_tor=use_tor, timeout=timeout, force_engine=force_engine
        )
        task_ids.append(task.id)

    return {
        "parent_task_id": self.request.id,
        "child_task_ids": task_ids,
        "total_urls": len(urls),
    }


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def search_dark_web_task(
    self,
    query: str,
    max_results: int = 50,
    scrape_results: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Celery task to search dark web search engines for .onion links.

    Optionally kicks off scrape tasks for each discovered URL.

    Args:
        query: Search keyword(s)
        max_results: Max number of results to return
        scrape_results: If True, auto-queue scrape tasks for found URLs
        timeout: Per-engine page load timeout
    """
    task_id = self.request.id
    logger.info(f"Starting dark web search task {task_id} for query: {query}")

    scraper = SeleniumScraper(
        selenium_hub_url=settings.SELENIUM_HUB_URL,
        use_tor=True,
        tor_host=settings.TOR_PROXY_HOST,
        tor_port=settings.TOR_HTTP_PORT,
        timeout=timeout,
        blacklisted_ips=settings.BLACKLISTED_IPS,
        require_tor_exit_node=settings.REQUIRE_TOR_EXIT_NODE,
    )

    driver = None
    try:
        driver = scraper._create_driver()

        # Verify anonymity before searching
        scraper.verify_anonymity(driver)

        results = search_dark_web(driver, query, timeout=timeout)

        # Limit results
        if len(results) > max_results:
            results = results[:max_results]

        # Optionally queue scrape tasks for discovered URLs
        child_task_ids = []
        if scrape_results and results:
            for result in results:
                task = scrape_url_task.delay(
                    url=result["link"],
                    use_tor=True,
                    timeout=timeout,
                )
                child_task_ids.append(task.id)

        logger.info(
            f"Search task {task_id} complete: "
            f"{len(results)} results, {len(child_task_ids)} scrape tasks queued"
        )

        return {
            "success": True,
            "query": query,
            "total_results": len(results),
            "results": results,
            "scrape_task_ids": child_task_ids,
        }

    except (IPLeakError, AnonymityVerificationError) as e:
        logger.critical(f"Search task {task_id} ABORTED: {str(e)}")
        return {
            "success": False,
            "query": query,
            "error": str(e),
            "security_abort": True,
        }

    except Exception as e:
        logger.error(f"Search task {task_id} failed: {str(e)}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {
            "success": False,
            "query": query,
            "error": str(e),
        }

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
