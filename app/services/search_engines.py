"""
Dark web search engine integration.

Provides a list of known .onion search engines and functions to query them
via Selenium Grid through Tor. Inspired by robin's search.py but adapted
for our Selenium-based architecture.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

SEARCH_ENGINES = [
    {
        "name": "Ahmia",
        "url": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={query}",
    },
    {
        "name": "Torch",
        "url": "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/cgi-bin/omega/omega?P={query}",
    },
    {
        "name": "Tor66",
        "url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={query}",
    },
    {
        "name": "OnionLand",
        "url": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={query}",
    },
    {
        "name": "Excavator",
        "url": "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search?query={query}",
    },
    {
        "name": "Amnesia",
        "url": "http://amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion/search?query={query}",
    },
    {
        "name": "Torgle",
        "url": "http://iy3544gmoeclh5de6gez2256v6pjh4omhpqdh2wpeeppjtvqmjhkfwad.onion/torgle/?query={query}",
    },
    {
        "name": "The Deep Searches",
        "url": "http://searchgf7gdtauh7bhnbyed4ivxqmuoat3nm6zfrg3ymkq6mtnpye3ad.onion/search?q={query}",
    },
]

ONION_LINK_PATTERN = re.compile(r"https?://[a-z2-7]{16,56}\.onion[^\s\"'<>]*")


def search_single_engine(
    driver: webdriver.Remote,
    engine: Dict[str, str],
    query: str,
    timeout: int = 30,
) -> List[Dict[str, str]]:
    """
    Search a single dark web search engine and extract .onion links.

    Args:
        driver: Active Selenium Remote WebDriver (already proxied through Tor)
        engine: Dict with 'name' and 'url' (url contains {query} placeholder)
        query: Search query string
        timeout: Page load timeout

    Returns:
        List of dicts with 'title', 'link', 'source' keys
    """
    engine_name = engine["name"]
    search_url = engine["url"].format(query=query)
    results = []

    try:
        logger.info(f"Searching {engine_name} for: {query}")
        driver.get(search_url)

        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        anchors = driver.find_elements(By.TAG_NAME, "a")
        seen_links = set()

        for anchor in anchors:
            try:
                href = anchor.get_attribute("href") or ""
                title = anchor.text.strip()

                onion_matches = ONION_LINK_PATTERN.findall(href)
                if not onion_matches:
                    continue

                link = onion_matches[0]

                # Skip self-referential search engine links
                if "search" in link.lower() and engine_name.lower() in link.lower():
                    continue

                # Skip if title is too short (likely a navigation element)
                if len(title) < 3:
                    title = link

                clean_link = link.rstrip("/")
                if clean_link not in seen_links:
                    seen_links.add(clean_link)
                    results.append({
                        "title": title,
                        "link": link,
                        "source": engine_name,
                    })

            except Exception:
                continue

        logger.info(f"{engine_name}: found {len(results)} results")

    except Exception as e:
        logger.warning(f"{engine_name} search failed: {str(e)}")

    return results


def search_dark_web(
    driver: webdriver.Remote,
    query: str,
    engines: Optional[List[Dict[str, str]]] = None,
    timeout: int = 30,
) -> List[Dict[str, str]]:
    """
    Search across multiple dark web search engines sequentially.

    Uses the same driver session (single Tor circuit) to search all engines.

    Args:
        driver: Active Selenium Remote WebDriver
        query: Search query string
        engines: Optional list of engines to use. Defaults to all SEARCH_ENGINES.
        timeout: Page load timeout per engine

    Returns:
        Deduplicated list of results with 'title', 'link', 'source' keys
    """
    if engines is None:
        engines = SEARCH_ENGINES

    all_results = []
    seen_links = set()

    for engine in engines:
        try:
            results = search_single_engine(driver, engine, query, timeout)
            for result in results:
                clean_link = result["link"].rstrip("/")
                if clean_link not in seen_links:
                    seen_links.add(clean_link)
                    all_results.append(result)
        except Exception as e:
            logger.warning(f"Skipping {engine['name']}: {str(e)}")
            continue

    logger.info(f"Total unique results for '{query}': {len(all_results)}")
    return all_results


def get_available_engines() -> List[Dict[str, str]]:
    """Return list of available search engines with name and URL template."""
    return [{"name": e["name"], "url_template": e["url"]} for e in SEARCH_ENGINES]
