from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://darkweb:darkweb_secret@db:5432/darkweb_scraper"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Selenium Grid
    SELENIUM_HUB_URL: str = "http://selenium-chrome:4444/wd/hub"

    # Tor Proxy
    TOR_PROXY_HOST: str = "tor-proxy"
    TOR_SOCKS_PORT: int = 9050
    TOR_HTTP_PORT: int = 8118

    # API Settings
    API_SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Scraper Settings
    SCRAPER_TIMEOUT: int = 30
    SCRAPER_MAX_RETRIES: int = 3
    SCRAPER_COOLDOWN: int = 60

    # Smart Scraping Strategy
    # Minimum content length (chars) from BS4 before escalating to Selenium
    BS4_MIN_CONTENT_LENGTH: int = 200
    # Default engine: "auto" (BS4 first, escalate if needed), "bs4", or "selenium"
    DEFAULT_SCRAPE_ENGINE: str = "auto"

    # IP Security - Blacklisted IPs (your real IPs that should NEVER be exposed)
    BLACKLISTED_IPS: List[str] = []
    
    # Abort scraping if IP is not a verified Tor exit node
    REQUIRE_TOR_EXIT_NODE: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
