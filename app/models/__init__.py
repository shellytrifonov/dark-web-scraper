"""Database models."""
from app.models.base import Base
from app.models.scraped_site import ScrapedSite
from app.models.scrape_job import ScrapeJob
from app.models.scraper_config import ScraperConfig
from app.models.site_monitor import SiteMonitor, UptimeRecord

__all__ = ["Base", "ScrapedSite", "ScrapeJob", "ScraperConfig", "SiteMonitor", "UptimeRecord"]
