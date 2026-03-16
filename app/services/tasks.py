import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from celery import shared_task
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.scraped_site import ScrapedSite
from app.models.scrape_job import ScrapeJob, JobStatus
from app.models.site_monitor import SiteMonitor, UptimeRecord
from app.services.selenium_scraper import (
    SeleniumScraper,
    IPLeakError,
    AnonymityVerificationError,
)
from app.services.smart_scraper import SmartScraper, ScrapeEngine
from app.services.search_engines import search_dark_web, SEARCH_ENGINES
from app.services.entity_extractor import EntityExtractor

logger = logging.getLogger(__name__)

SYNC_DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSession = sessionmaker(bind=sync_engine)


def _extract_meta_description(html: str) -> Optional[str]:
    """Extract meta description from raw HTML."""
    if not html:
        return None
    import re
    match = re.search(
        r'<meta\s+[^>]*name=["\']description["\']\s+[^>]*content=["\']([^"\']*)["\']',
        html, re.IGNORECASE
    )
    if not match:
        match = re.search(
            r'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*name=["\']description["\']',
            html, re.IGNORECASE
        )
    return match.group(1).strip()[:1024] if match else None


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
        # Reuse existing job on retries instead of creating duplicates
        job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
        if job:
            job.status = JobStatus.RUNNING.value
            job.error_message = None
            job.retries = self.request.retries
        else:
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
            tor_socks_port=settings.TOR_SOCKS_PORT,
            timeout=timeout,
            use_tor=use_tor,
            blacklisted_ips=settings.BLACKLISTED_IPS,
            require_tor_exit_node=settings.REQUIRE_TOR_EXIT_NODE,
            min_content_length=settings.BS4_MIN_CONTENT_LENGTH,
        )

        scrape_start = time.time()
        result = scraper.scrape(url, engine=engine)
        scrape_duration_ms = int((time.time() - scrape_start) * 1000)

        clean_content = result.get("clean_content") or result.get("content") or ""
        html_raw = result.get("html") or ""
        found_links = result.get("links", [])

        # Extract meta description from HTML
        meta_desc = _extract_meta_description(html_raw)

        # Entity extraction (regex always, LLM if API key provided)
        extractor = EntityExtractor(
            llm_api_key=settings.LLM_API_KEY or None,
            llm_model=settings.LLM_MODEL,
        )
        entities = extractor.extract(clean_content, url=url)
        logger.info(
            f"Entity extraction for {url}: {entities.get('total_entities', 0)} entities found"
        )

        scraped_site = ScrapedSite(
            url=url,
            title=result.get("title"),
            content=clean_content,
            html_content=html_raw,
            status_code=result.get("status_code"),
            engine_used=result.get("engine_used"),
            escalated=result.get("escalated", False),
            content_length=len(clean_content),
            html_size_bytes=len(html_raw.encode("utf-8")) if html_raw else 0,
            links_count=len(found_links),
            links=json.dumps(found_links[:100]),  # cap at 100 links
            meta_description=meta_desc,
            response_time_ms=scrape_duration_ms,
            entities=entities,
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
            "content_length": len(clean_content),
            "scraped_site_id": scraped_site.id,
            "engine_used": result.get("engine_used"),
            "escalated": result.get("escalated", False),
            "links_count": len(found_links),
            "response_time_ms": scrape_duration_ms,
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

        will_retry = self.request.retries < self.max_retries

        try:
            job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
            if job:
                if will_retry:
                    # Keep as RUNNING — the retry will pick it up
                    job.error_message = f"Retry {self.request.retries + 1}/{self.max_retries}: {str(e)}"
                    job.retries = self.request.retries
                else:
                    job.status = JobStatus.FAILED.value
                    job.error_message = str(e)
                    job.retries = self.request.retries
                    job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass

        if will_retry:
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

    session = SyncSession()
    driver = None

    try:
        # Track search as a job so it appears in the Job Monitor
        job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
        if job:
            job.status = JobStatus.RUNNING.value
            job.error_message = None
            job.retries = self.request.retries
        else:
            job = ScrapeJob(
                celery_task_id=task_id,
                target_url=f"search://{query}",
                status=JobStatus.RUNNING.value,
                started_at=datetime.utcnow(),
            )
            session.add(job)
        session.commit()

        scraper = SeleniumScraper(
            selenium_hub_url=settings.SELENIUM_HUB_URL,
            use_tor=True,
            tor_host=settings.TOR_PROXY_HOST,
            tor_port=settings.TOR_HTTP_PORT,
            tor_socks_port=settings.TOR_SOCKS_PORT,
            timeout=timeout,
            blacklisted_ips=settings.BLACKLISTED_IPS,
            require_tor_exit_node=settings.REQUIRE_TOR_EXIT_NODE,
        )

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

        # Mark job complete
        try:
            job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
            if job:
                job.status = JobStatus.COMPLETED.value
                job.completed_at = datetime.utcnow()
                job.error_message = f"{len(results)} results found"
                session.commit()
        except Exception:
            pass

        return {
            "success": True,
            "query": query,
            "total_results": len(results),
            "results": results,
            "scrape_task_ids": child_task_ids,
        }

    except (IPLeakError, AnonymityVerificationError) as e:
        logger.critical(f"Search task {task_id} ABORTED: {str(e)}")
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
            "query": query,
            "error": str(e),
            "security_abort": True,
        }

    except Exception as e:
        logger.error(f"Search task {task_id} failed: {str(e)}")
        will_retry = self.request.retries < self.max_retries
        try:
            job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
            if job:
                if will_retry:
                    job.error_message = f"Retry {self.request.retries + 1}/{self.max_retries}: {str(e)}"
                    job.retries = self.request.retries
                else:
                    job.status = JobStatus.FAILED.value
                    job.error_message = str(e)
                    job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass
        if will_retry:
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
        session.close()


# ---------------------------------------------------------------------------
# Content diff helpers
# ---------------------------------------------------------------------------

def _content_hash(html: str) -> str:
    """SHA-256 hash of HTML content for change detection."""
    return hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()


def _compare_content(old_html: str, new_html: str) -> Dict[str, Any]:
    """Compare two HTML snapshots and return a change summary."""
    old_len = len(old_html)
    new_len = len(new_html)
    delta = new_len - old_len
    pct = round(abs(delta) / max(old_len, 1) * 100, 1)
    direction = "grew" if delta > 0 else "shrank" if delta < 0 else "unchanged"

    return {
        "changed": _content_hash(old_html) != _content_hash(new_html),
        "size_delta_bytes": delta,
        "summary": f"Content {direction} by {pct}% ({abs(delta):,} bytes)",
    }


# ---------------------------------------------------------------------------
# Site Pulse – periodic monitoring task
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=1, default_retry_delay=30)
def monitor_site_task(
    self,
    monitor_id: int,
    url: str,
    use_tor: bool = True,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Check a single monitored site: scrape it, record uptime,
    detect content changes, and update the SiteMonitor record.
    """
    task_id = self.request.id
    logger.info(f"Monitor check {task_id} for {url} (monitor_id={monitor_id})")

    session = SyncSession()
    job = None
    scrape_start = time.time()

    try:
        # Track monitor checks in ScrapeJob so they appear in Job Monitor
        job = session.query(ScrapeJob).filter_by(celery_task_id=task_id).first()
        if job:
            job.status = JobStatus.RUNNING.value
            job.error_message = None
            job.retries = self.request.retries
        else:
            job = ScrapeJob(
                celery_task_id=task_id,
                target_url=f"monitor://{url}",
                status=JobStatus.RUNNING.value,
                started_at=datetime.utcnow(),
            )
            session.add(job)
        session.commit()

        monitor = session.query(SiteMonitor).filter_by(id=monitor_id).first()
        if not monitor or not monitor.is_active:
            logger.info(f"Monitor {monitor_id} inactive or missing, skipping")
            return {"success": False, "reason": "monitor_inactive"}

        # Scrape the site
        scraper = SmartScraper(
            selenium_hub_url=settings.SELENIUM_HUB_URL,
            tor_host=settings.TOR_PROXY_HOST,
            tor_port=settings.TOR_HTTP_PORT,
            tor_socks_port=settings.TOR_SOCKS_PORT,
            timeout=timeout,
            use_tor=use_tor,
            blacklisted_ips=settings.BLACKLISTED_IPS,
            require_tor_exit_node=settings.REQUIRE_TOR_EXIT_NODE,
            min_content_length=settings.BS4_MIN_CONTENT_LENGTH,
        )

        result = scraper.scrape(url, engine="auto")
        response_ms = int((time.time() - scrape_start) * 1000)

        html_raw = result.get("html") or ""
        new_hash = _content_hash(html_raw) if html_raw else ""
        status_code = result.get("status_code")

        # Determine if site is up
        site_status = "up"
        if status_code and status_code >= 400:
            site_status = "down"
        elif status_code == 408:
            site_status = "timeout"

        # Content diff against previous version
        content_changed = False
        change_summary = None
        size_delta = None

        if monitor.last_content_hash and new_hash:
            if new_hash != monitor.last_content_hash:
                content_changed = True
                # Fetch previous scraped record to compute diff summary
                prev = (
                    session.query(ScrapedSite)
                    .filter_by(url=url)
                    .order_by(desc(ScrapedSite.scraped_at))
                    .first()
                )
                if prev and prev.html_content:
                    diff = _compare_content(prev.html_content, html_raw)
                    change_summary = diff["summary"]
                    size_delta = diff["size_delta_bytes"]
                else:
                    change_summary = "New content detected (no previous HTML to compare)"

        # Record uptime entry
        uptime = UptimeRecord(
            monitor_id=monitor_id,
            url=url,
            checked_at=datetime.utcnow(),
            status=site_status,
            status_code=status_code,
            response_time_ms=response_ms,
            content_changed=content_changed,
            content_hash=new_hash,
            change_summary=change_summary,
            size_delta_bytes=size_delta,
        )
        session.add(uptime)

        # Save scraped content (entity extraction included)
        clean_content = result.get("clean_content") or result.get("content") or ""
        found_links = result.get("links", [])
        meta_desc = _extract_meta_description(html_raw)

        extractor = EntityExtractor(
            llm_api_key=settings.LLM_API_KEY or None,
            llm_model=settings.LLM_MODEL,
        )
        entities = extractor.extract(clean_content, url=url)

        scraped_site = ScrapedSite(
            url=url,
            title=result.get("title"),
            content=clean_content,
            html_content=html_raw,
            status_code=status_code,
            engine_used=result.get("engine_used"),
            escalated=result.get("escalated", False),
            content_length=len(clean_content),
            html_size_bytes=len(html_raw.encode("utf-8")) if html_raw else 0,
            links_count=len(found_links),
            links=json.dumps(found_links[:100]),
            meta_description=meta_desc,
            response_time_ms=response_ms,
            entities=entities,
            scraped_at=datetime.utcnow(),
        )
        session.add(scraped_site)

        # Update monitor record
        monitor.last_checked_at = datetime.utcnow()
        monitor.last_status = site_status
        monitor.last_content_hash = new_hash
        monitor.total_checks += 1
        if site_status == "up":
            monitor.successful_checks += 1
        if content_changed:
            monitor.version_count += 1
            monitor.last_change_at = datetime.utcnow()
            monitor.last_change_summary = change_summary

        session.commit()

        if job:
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.utcnow()
            job.error_message = change_summary or f"status={site_status}"
            session.commit()

        logger.info(
            f"Monitor check {task_id} done: status={site_status}, "
            f"changed={content_changed}, {response_ms}ms"
        )

        return {
            "success": True,
            "monitor_id": monitor_id,
            "url": url,
            "status": site_status,
            "content_changed": content_changed,
            "change_summary": change_summary,
            "response_time_ms": response_ms,
        }

    except Exception as e:
        response_ms = int((time.time() - scrape_start) * 1000)
        logger.error(f"Monitor check {task_id} failed: {e}")

        try:
            monitor = session.query(SiteMonitor).filter_by(id=monitor_id).first()
            if monitor:
                monitor.last_checked_at = datetime.utcnow()
                monitor.last_status = "error"
                monitor.total_checks += 1

            uptime = UptimeRecord(
                monitor_id=monitor_id,
                url=url,
                checked_at=datetime.utcnow(),
                status="error",
                response_time_ms=response_ms,
                error_message=str(e)[:500],
            )
            session.add(uptime)
            session.commit()

            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = str(e)[:500]
                job.completed_at = datetime.utcnow()
                session.commit()
        except Exception:
            pass

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {"success": False, "monitor_id": monitor_id, "error": str(e)}

    finally:
        session.close()


@shared_task
def run_site_monitors() -> Dict[str, Any]:
    """
    Periodic Beat task: find all active monitors whose next check
    is due and dispatch a monitor_site_task for each.
    """
    session = SyncSession()
    try:
        monitors = (
            session.query(SiteMonitor)
            .filter_by(is_active=True)
            .all()
        )

        dispatched = []
        now = datetime.utcnow()
        for mon in monitors:
            # Check if enough time has passed since last check
            if mon.last_checked_at:
                next_due = mon.last_checked_at + timedelta(hours=mon.frequency_hours)
                if now < next_due:
                    continue

            task = monitor_site_task.delay(
                monitor_id=mon.id,
                url=mon.url,
            )
            dispatched.append({"monitor_id": mon.id, "url": mon.url, "task_id": task.id})
            logger.info(f"Dispatched monitor check for {mon.url} (monitor_id={mon.id})")

        return {
            "checked_at": now.isoformat(),
            "total_active": len(monitors),
            "dispatched": len(dispatched),
            "tasks": dispatched,
        }

    finally:
        session.close()
