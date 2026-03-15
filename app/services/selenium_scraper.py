import json
import logging
import random
import re
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)

# Rotating user agents to reduce fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux i686; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


class IPLeakError(Exception):
    """Raised when potential IP leak is detected."""
    pass


class AnonymityVerificationError(Exception):
    """Raised when anonymity cannot be verified."""
    pass


class SeleniumScraper:
    """
    Selenium-based web scraper that connects to a remote Selenium Grid.
    
    Supports routing traffic through Tor proxy for anonymity.
    """

    def __init__(
        self,
        selenium_hub_url: str,
        use_tor: bool = True,
        tor_host: str = "tor-proxy",
        tor_port: int = 8118,
        tor_socks_port: int = 9050,
        timeout: int = 30,
        blacklisted_ips: Optional[List[str]] = None,
        require_tor_exit_node: bool = True,
    ):
        self.selenium_hub_url = selenium_hub_url
        self.use_tor = use_tor
        self.tor_host = tor_host
        self.tor_port = tor_port
        self.tor_socks_port = tor_socks_port
        self.timeout = timeout
        self.blacklisted_ips = blacklisted_ips or []
        self.require_tor_exit_node = require_tor_exit_node

    def _create_driver(self) -> webdriver.Remote:
        """Create a remote WebDriver instance with privacy-hardened options."""
        options = Options()

        # Basic headless configuration
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # Anti-detection
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # ============================================
        # WebRTC Leak Prevention
        # ============================================
        options.add_argument("--disable-webrtc")
        options.add_argument("--disable-rtc-smoothness-algorithm")
        options.add_argument("--disable-webrtc-hw-decoding")
        options.add_argument("--disable-webrtc-hw-encoding")
        options.add_argument("--disable-webrtc-multiple-routes")
        options.add_argument("--disable-webrtc-hw-vp8-encoding")
        options.add_argument("--enforce-webrtc-ip-permission-check")
        options.add_argument("--force-webrtc-ip-handling-policy=disable_non_proxied_udp")

        # ============================================
        # Fingerprinting Prevention
        # ============================================
        options.add_argument("--disable-reading-from-canvas")
        options.add_argument("--disable-3d-apis")
        options.add_argument("--disable-accelerated-2d-canvas")
        options.add_argument("--disable-accelerated-jpeg-decoding")
        options.add_argument("--disable-accelerated-mjpeg-decode")
        options.add_argument("--disable-accelerated-video-decode")
        options.add_argument("--disable-audio-output")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-canvas-aa")
        options.add_argument("--disable-composited-antialiasing")
        options.add_argument("--disable-gl-extensions")
        options.add_argument("--disable-speech-api")
        options.add_argument("--disable-voice-input")
        options.add_argument("--disable-wake-on-wifi")
        options.add_argument("--disable-webgl")
        options.add_argument("--disable-webgl2")

        # Disable features that can be used for fingerprinting
        options.add_argument("--disable-features=AudioServiceOutOfProcess")
        options.add_argument("--disable-features=IsolateOrigins")
        options.add_argument("--disable-features=site-per-process")
        
        # Disable plugins and extensions
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-plugins-discovery")
        options.add_argument("--disable-extensions")

        # Disable local storage tracking
        options.add_argument("--disable-local-storage")
        options.add_argument("--disable-databases")

        # Rotating user agent per session
        self._current_user_agent = random.choice(USER_AGENTS)
        options.add_argument(f"--user-agent={self._current_user_agent}")

        # ============================================
        # Proxy Configuration (Tor via SOCKS5)
        # ============================================
        if self.use_tor:
            socks_address = f"{self.tor_host}:{self.tor_socks_port}"
            options.add_argument(f"--proxy-server=socks5://{socks_address}")
            # Force all DNS through the SOCKS5 proxy (resolves .onion natively)
            options.add_argument("--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE localhost, tor-proxy")

        # Chrome preferences for additional privacy
        prefs = {
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "webrtc.multiple_routes_enabled": False,
            "webrtc.nonproxied_udp_enabled": False,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_setting_values.media_stream_mic": 2,
            "profile.default_content_setting_values.media_stream_camera": 2,
            "profile.managed_default_content_settings.images": 1,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
        }
        options.add_experimental_option("prefs", prefs)

        driver = webdriver.Remote(
            command_executor=self.selenium_hub_url,
            options=options,
        )
        driver.set_page_load_timeout(self.timeout)

        # Execute CDP commands for additional WebRTC blocking and UA override
        try:
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": self._current_user_agent
            })
        except Exception:
            pass

        return driver

    def verify_anonymity(self, driver: webdriver.Remote) -> Dict[str, Any]:
        """
        Pre-scrape verification: Check current IP through proxy.
        
        Aborts if:
        - IP matches any blacklisted IP (your real IP)
        - IP is not a verified Tor exit node (when require_tor_exit_node=True)
        
        Returns:
            Dictionary with verification results
            
        Raises:
            IPLeakError: If blacklisted IP is detected
            AnonymityVerificationError: If not using Tor exit node
        """
        logger.info("Starting pre-scrape anonymity verification...")
        
        try:
            driver.get("https://check.torproject.org/api/ip")
            
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            body = driver.find_element(By.TAG_NAME, "body")
            data = json.loads(body.text)
            
            current_ip = data.get("IP")
            is_tor = data.get("IsTor", False)
            
            logger.info(f"Anonymity check - IP: {current_ip}, Is Tor: {is_tor}")
            
            # Check against blacklist (your real IPs)
            if current_ip and self.blacklisted_ips:
                for blacklisted_ip in self.blacklisted_ips:
                    if current_ip == blacklisted_ip:
                        error_msg = (
                            f"CRITICAL: Blacklisted IP detected! "
                            f"Current IP {current_ip} matches blacklist. "
                            f"Aborting to prevent identity exposure."
                        )
                        logger.critical(error_msg)
                        raise IPLeakError(error_msg)
            
            # Verify Tor exit node if required
            if self.require_tor_exit_node and not is_tor:
                error_msg = (
                    f"Anonymity verification failed! "
                    f"IP {current_ip} is NOT a Tor exit node. "
                    f"Aborting to prevent identity exposure."
                )
                logger.error(error_msg)
                raise AnonymityVerificationError(error_msg)
            
            verification_result = {
                "verified": True,
                "ip": current_ip,
                "is_tor_exit_node": is_tor,
                "blacklist_check": "passed",
            }
            
            logger.info(f"Anonymity verification PASSED: {verification_result}")
            return verification_result
            
        except (IPLeakError, AnonymityVerificationError):
            raise
        except Exception as e:
            error_msg = f"Failed to verify anonymity (transient): {str(e)}"
            logger.warning(error_msg)
            # Transient errors (proxy unreachable, timeout, DNS) are NOT
            # security violations — they should be retried, not aborted.
            # Raise generic Exception so the task retry logic handles it.
            raise RuntimeError(error_msg) from e

    def scrape(self, url: str, skip_verification: bool = False) -> Dict[str, Any]:
        """
        Scrape a URL and return the extracted content.
        
        Performs pre-scrape anonymity verification unless skip_verification=True.
        
        Args:
            url: The URL to scrape
            skip_verification: Skip anonymity check (NOT RECOMMENDED)
            
        Returns:
            Dictionary containing:
                - title: Page title
                - content: Text content
                - html: Full HTML content
                - status_code: HTTP status (approximated)
                - links: List of links found on page
                - anonymity: Verification results
                
        Raises:
            IPLeakError: If blacklisted IP detected
            AnonymityVerificationError: If not using Tor exit node
        """
        driver = None
        result = {
            "url": url,
            "title": None,
            "content": None,
            "html": None,
            "status_code": None,
            "links": [],
            "anonymity": None,
        }

        try:
            logger.info(f"Creating WebDriver for URL: {url}")
            driver = self._create_driver()

            # Pre-scrape anonymity verification
            if not skip_verification and self.use_tor:
                result["anonymity"] = self.verify_anonymity(driver)

            logger.info(f"Navigating to: {url}")
            driver.get(url)

            WebDriverWait(driver, self.timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            result["title"] = driver.title
            result["html"] = driver.page_source

            try:
                body = driver.find_element(By.TAG_NAME, "body")
                result["content"] = body.text
            except Exception:
                result["content"] = ""

            # Clean HTML: strip scripts, styles, and normalize whitespace
            result["clean_content"] = self._clean_html(result["html"])

            try:
                links = driver.find_elements(By.TAG_NAME, "a")
                result["links"] = [
                    link.get_attribute("href")
                    for link in links
                    if link.get_attribute("href")
                ]
            except Exception:
                pass

            result["status_code"] = 200

            logger.info(f"Successfully scraped: {url}")

        except TimeoutException:
            logger.error(f"Timeout while scraping: {url}")
            result["status_code"] = 408
            raise

        except WebDriverException as e:
            logger.error(f"WebDriver error while scraping {url}: {str(e)}")
            result["status_code"] = 500
            raise

        except Exception as e:
            logger.error(f"Unexpected error while scraping {url}: {str(e)}")
            raise

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        return result

    @staticmethod
    def _clean_html(html: Optional[str]) -> str:
        """
        Strip scripts, styles, and HTML tags from raw HTML.

        Returns cleaned, normalized plain text.
        """
        if not html:
            return ""
        text = html
        # Remove script and style blocks entirely
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        # Remove all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ")
        # Normalize whitespace
        text = " ".join(text.split())
        return text.strip()

    def check_tor_connection(self) -> Dict[str, Any]:
        """
        Verify that traffic is being routed through Tor.
        
        Returns:
            Dictionary with Tor connection status and IP
        """
        driver = None
        try:
            driver = self._create_driver()
            driver.get("https://check.torproject.org/api/ip")

            body = driver.find_element(By.TAG_NAME, "body")
            data = json.loads(body.text)

            return {
                "is_tor": data.get("IsTor", False),
                "ip": data.get("IP"),
            }

        except Exception as e:
            logger.error(f"Failed to check Tor connection: {str(e)}")
            return {"is_tor": False, "error": str(e)}

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
