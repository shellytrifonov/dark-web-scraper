"""
Lightweight BeautifulSoup4 scraper engine.

Uses requests + BS4 through the Tor HTTP proxy. Much faster and lighter
than Selenium but cannot handle JavaScript-rendered pages.
"""

import logging
import random
import re
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.services.selenium_scraper import USER_AGENTS

logger = logging.getLogger(__name__)

# Patterns that indicate JavaScript is required for content rendering
JS_REQUIRED_PATTERNS = [
    r"you need to enable javascript",
    r"javascript is required",
    r"please enable javascript",
    r"this site requires javascript",
    r"javascript must be enabled",
    r"enable javascript to view",
    r"this page requires javascript",
    r"<noscript>",
    r"document\.write\(",
    r"window\.onload",
    r"react-root",
    r"__next",
    r"cf-browser-verification",
    r"checking your browser",
    r"just a moment\.\.\.",
    r"attention required",
    r"please wait while we verify",
]

JS_REQUIRED_RE = re.compile(
    "|".join(JS_REQUIRED_PATTERNS), re.IGNORECASE
)


class BS4Scraper:
    """
    Lightweight scraper using requests + BeautifulSoup4.

    Routes traffic through Tor HTTP proxy (Privoxy) for anonymity.
    """

    def __init__(
        self,
        tor_host: str = "tor-proxy",
        tor_port: int = 8118,
        timeout: int = 30,
        use_tor: bool = True,
    ):
        self.tor_host = tor_host
        self.tor_port = tor_port
        self.timeout = timeout
        self.use_tor = use_tor

    def _create_session(self) -> requests.Session:
        """Create a requests session with Tor proxy and retry logic."""
        session = requests.Session()

        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        if self.use_tor:
            proxy_url = f"http://{self.tor_host}:{self.tor_port}"
            session.proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }

        session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        return session

    def scrape(self, url: str) -> Dict[str, Any]:
        """
        Scrape a URL using requests + BeautifulSoup.

        Args:
            url: Target URL to scrape

        Returns:
            Dictionary with scraped content and metadata
        """
        result = {
            "url": url,
            "title": None,
            "content": None,
            "clean_content": None,
            "html": None,
            "status_code": None,
            "links": [],
            "engine": "bs4",
            "needs_js": False,
        }

        session = self._create_session()

        try:
            logger.info(f"[BS4] Scraping: {url}")
            response = session.get(url, timeout=self.timeout, verify=False)
            result["status_code"] = response.status_code

            if response.status_code != 200:
                logger.warning(f"[BS4] HTTP {response.status_code} for {url}")
                return result

            raw_html = response.text
            result["html"] = raw_html

            soup = BeautifulSoup(raw_html, "lxml")

            # Extract title
            title_tag = soup.find("title")
            result["title"] = title_tag.get_text(strip=True) if title_tag else None

            # Remove scripts and styles before extracting text
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            # Extract clean text content
            text = soup.get_text(separator=" ")
            text = " ".join(text.split())  # normalize whitespace
            result["content"] = text
            result["clean_content"] = text

            # Extract links
            result["links"] = [
                a.get("href")
                for a in soup.find_all("a", href=True)
                if a.get("href")
            ]

            # Check if the page likely needs JavaScript
            result["needs_js"] = self._detect_js_requirement(raw_html, text)

            if result["needs_js"]:
                logger.info(f"[BS4] JavaScript likely required for: {url}")

            logger.info(
                f"[BS4] Done: {url} — "
                f"{len(text)} chars, {len(result['links'])} links, "
                f"needs_js={result['needs_js']}"
            )

        except requests.exceptions.Timeout:
            logger.error(f"[BS4] Timeout: {url}")
            result["status_code"] = 408
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[BS4] Connection error for {url}: {str(e)}")
            result["status_code"] = 503
        except Exception as e:
            logger.error(f"[BS4] Error scraping {url}: {str(e)}")
            result["status_code"] = 500

        return result

    @staticmethod
    def _detect_js_requirement(raw_html: str, clean_text: str) -> bool:
        """
        Heuristic check: does this page require JavaScript to render?

        Checks:
        - Known JS-required string patterns in the raw HTML
        - Very short clean text relative to HTML size (JS-rendered content)
        """
        # Check for explicit JS-required patterns
        if JS_REQUIRED_RE.search(raw_html):
            return True

        # If HTML is substantial but extracted text is tiny, likely JS-rendered
        html_len = len(raw_html)
        text_len = len(clean_text)

        if html_len > 2000 and text_len < 100:
            return True

        # High ratio of HTML to text suggests heavy JS framework
        if html_len > 5000 and text_len > 0 and (html_len / text_len) > 50:
            return True

        return False
