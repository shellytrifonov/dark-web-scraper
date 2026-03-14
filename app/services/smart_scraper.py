"""
Smart Scraping Strategy orchestrator.

Implements a two-tier scraping approach:
1. Try BS4 first (fast, lightweight)
2. Auto-escalate to Selenium if BS4 output indicates JavaScript is required

Users can also force a specific engine via the `force_engine` parameter.
"""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from app.services.bs4_scraper import BS4Scraper
from app.services.selenium_scraper import (
    SeleniumScraper,
    IPLeakError,
    AnonymityVerificationError,
)

logger = logging.getLogger(__name__)


class ScrapeEngine(str, Enum):
    """Available scraping engines."""
    AUTO = "auto"
    BS4 = "bs4"
    SELENIUM = "selenium"


class SmartScraper:
    """
    Orchestrates scraping using a smart fallback strategy.

    - `auto`: Try BS4 first. If the page needs JS, escalate to Selenium.
    - `bs4`: Force BS4 only (fastest, no JS support).
    - `selenium`: Force Selenium only (full JS rendering).
    """

    def __init__(
        self,
        selenium_hub_url: str,
        tor_host: str = "tor-proxy",
        tor_port: int = 8118,
        timeout: int = 30,
        use_tor: bool = True,
        blacklisted_ips: Optional[List[str]] = None,
        require_tor_exit_node: bool = True,
        min_content_length: int = 200,
    ):
        self.selenium_hub_url = selenium_hub_url
        self.tor_host = tor_host
        self.tor_port = tor_port
        self.timeout = timeout
        self.use_tor = use_tor
        self.blacklisted_ips = blacklisted_ips or []
        self.require_tor_exit_node = require_tor_exit_node
        self.min_content_length = min_content_length

    def _create_bs4_scraper(self) -> BS4Scraper:
        return BS4Scraper(
            tor_host=self.tor_host,
            tor_port=self.tor_port,
            timeout=self.timeout,
            use_tor=self.use_tor,
        )

    def _create_selenium_scraper(self) -> SeleniumScraper:
        return SeleniumScraper(
            selenium_hub_url=self.selenium_hub_url,
            use_tor=self.use_tor,
            tor_host=self.tor_host,
            tor_port=self.tor_port,
            timeout=self.timeout,
            blacklisted_ips=self.blacklisted_ips,
            require_tor_exit_node=self.require_tor_exit_node,
        )

    def _should_escalate(self, bs4_result: Dict[str, Any]) -> bool:
        """
        Determine if BS4 result is insufficient and Selenium is needed.

        Escalation triggers:
        - BS4 detected JS-required patterns
        - Content is shorter than the configured minimum
        - HTTP error (non-200 status that Selenium might handle differently)
        - No content extracted at all
        """
        # Explicit JS detection by BS4
        if bs4_result.get("needs_js"):
            logger.info("[Smart] Escalating: JS-required patterns detected")
            return True

        content = bs4_result.get("clean_content") or bs4_result.get("content") or ""

        # No content at all
        if not content.strip():
            logger.info("[Smart] Escalating: no content extracted")
            return True

        # Content too short
        if len(content.strip()) < self.min_content_length:
            logger.info(
                f"[Smart] Escalating: content too short "
                f"({len(content.strip())} < {self.min_content_length} chars)"
            )
            return True

        # Connection-level failure that Selenium might handle via its own proxy setup
        status = bs4_result.get("status_code")
        if status and status >= 400:
            logger.info(f"[Smart] Escalating: HTTP {status}")
            return True

        return False

    def scrape(
        self,
        url: str,
        engine: ScrapeEngine = ScrapeEngine.AUTO,
        skip_verification: bool = False,
    ) -> Dict[str, Any]:
        """
        Scrape a URL using the smart strategy.

        Args:
            url: Target URL
            engine: Which engine to use ("auto", "bs4", "selenium")
            skip_verification: Skip Selenium anonymity check (not recommended)

        Returns:
            Scraping result dict with added `engine_used` and `escalated` fields

        Raises:
            IPLeakError: If blacklisted IP detected (Selenium path)
            AnonymityVerificationError: If Tor exit node check fails (Selenium path)
        """
        logger.info(f"[Smart] Scraping {url} with engine={engine.value}")

        # ── Force BS4 ──
        if engine == ScrapeEngine.BS4:
            result = self._scrape_with_bs4(url)
            result["engine_used"] = "bs4"
            result["escalated"] = False
            return result

        # ── Force Selenium ──
        if engine == ScrapeEngine.SELENIUM:
            result = self._scrape_with_selenium(url, skip_verification)
            result["engine_used"] = "selenium"
            result["escalated"] = False
            return result

        # ── Auto: BS4 first, escalate if needed ──
        bs4_result = self._scrape_with_bs4(url)

        if not self._should_escalate(bs4_result):
            logger.info(f"[Smart] BS4 sufficient for {url}")
            bs4_result["engine_used"] = "bs4"
            bs4_result["escalated"] = False
            return bs4_result

        # Escalate to Selenium
        logger.info(f"[Smart] Escalating to Selenium for {url}")
        selenium_result = self._scrape_with_selenium(url, skip_verification)
        selenium_result["engine_used"] = "selenium"
        selenium_result["escalated"] = True
        selenium_result["bs4_attempt"] = {
            "content_length": len(bs4_result.get("content") or ""),
            "needs_js": bs4_result.get("needs_js", False),
            "status_code": bs4_result.get("status_code"),
        }
        return selenium_result

    def _scrape_with_bs4(self, url: str) -> Dict[str, Any]:
        """Run BS4 scraper."""
        scraper = self._create_bs4_scraper()
        return scraper.scrape(url)

    def _scrape_with_selenium(
        self, url: str, skip_verification: bool = False
    ) -> Dict[str, Any]:
        """Run Selenium scraper."""
        scraper = self._create_selenium_scraper()
        result = scraper.scrape(url, skip_verification=skip_verification)
        result["engine"] = "selenium"
        return result
