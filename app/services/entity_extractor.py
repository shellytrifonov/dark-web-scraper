"""
Entity Extraction Service

Hybrid pipeline that extracts intelligence-relevant entities from scraped
dark web content using regex patterns, and optionally enriches results
with LLM-based semantic analysis (summary, legitimacy, category).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for entity extraction
# ---------------------------------------------------------------------------

# Bitcoin legacy (1...) and SegWit (bc1..., 3...)
_BTC_LEGACY = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
_BTC_SEGWIT = re.compile(r"\bbc1[a-zA-HJ-NP-Z0-9]{25,62}\b")

# Ethereum (0x...)
_ETH = re.compile(r"\b0x[0-9a-fA-F]{40}\b")

# PGP public key blocks
_PGP_BLOCK = re.compile(
    r"-----BEGIN PGP PUBLIC KEY BLOCK-----[\s\S]*?-----END PGP PUBLIC KEY BLOCK-----"
)

# Email addresses
_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# .onion URLs (v2 16-char and v3 56-char)
_ONION_URL = re.compile(
    r"https?://[a-z2-7]{16,56}\.onion(?:[/\w\-.~:/?#\[\]@!$&'()*+,;=%]*)?"
)

# Bare onion hostnames (no scheme)
_ONION_HOST = re.compile(r"\b[a-z2-7]{16,56}\.onion\b")

# Max text length sent to the LLM (characters). ~4000 tokens ≈ 16 000 chars.
_LLM_MAX_CHARS = 12_000

# LLM system prompt
_LLM_SYSTEM_PROMPT = """\
You are a dark-web intelligence analyst. Given the text content of a scraped \
.onion page, produce a JSON object with exactly these keys:

1. "summary": A single-sentence executive summary of what the site offers.
2. "legitimacy_score": An integer from 0 (clearly a scam) to 100 (appears \
legitimate), based on linguistic cues, promises made, and typical scam patterns.
3. "legitimacy_reason": A one-sentence explanation of the score.
4. "category": Exactly one of: "Market", "Forum", "News", "Personal", \
"Financial", "Hosting", "Search Engine", "Communication", "Other".

Return ONLY valid JSON. No markdown, no commentary."""


class EntityExtractor:
    """
    Extracts structured intelligence entities from scraped text content.

    Two extraction layers:
    - **Regex** (always runs): crypto wallets, PGP keys, emails, onion links.
    - **LLM** (optional): executive summary, legitimacy scoring, site category.
    """

    def __init__(self, llm_api_key: Optional[str] = None, llm_model: str = "gpt-4o-mini"):
        self.llm_api_key = llm_api_key.strip() if llm_api_key else None
        self.llm_model = llm_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, text: str, url: str = "") -> Dict[str, Any]:
        """
        Run the full extraction pipeline on *text*.

        Returns a dict with keys:
            crypto_wallets, pgp_keys, emails, onion_links   (regex)
            llm_summary, llm_legitimacy_score,
            llm_legitimacy_reason, llm_category              (LLM, if enabled)
        """
        if not text:
            return self._empty_result()

        result: Dict[str, Any] = {}

        # --- Regex extraction (always) ---
        result["crypto_wallets"] = self._extract_crypto(text)
        result["pgp_keys"] = self._extract_pgp(text)
        result["emails"] = self._extract_emails(text)
        result["onion_links"] = self._extract_onion_links(text, source_url=url)

        # --- LLM analysis (optional) ---
        if self.llm_api_key:
            llm_data = self._analyze_with_llm(text)
            result["llm_summary"] = llm_data.get("summary")
            result["llm_legitimacy_score"] = llm_data.get("legitimacy_score")
            result["llm_legitimacy_reason"] = llm_data.get("legitimacy_reason")
            result["llm_category"] = llm_data.get("category")
        else:
            result["llm_summary"] = None
            result["llm_legitimacy_score"] = None
            result["llm_legitimacy_reason"] = None
            result["llm_category"] = None

        # Convenience counts
        result["total_entities"] = (
            len(result["crypto_wallets"])
            + len(result["pgp_keys"])
            + len(result["emails"])
            + len(result["onion_links"])
        )

        return result

    # ------------------------------------------------------------------
    # Regex helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_crypto(text: str) -> List[Dict[str, str]]:
        """Find Bitcoin and Ethereum wallet addresses."""
        wallets: List[Dict[str, str]] = []
        seen: set = set()

        for match in _BTC_LEGACY.findall(text):
            if match not in seen:
                seen.add(match)
                wallets.append({"type": "BTC", "address": match})

        for match in _BTC_SEGWIT.findall(text):
            if match not in seen:
                seen.add(match)
                wallets.append({"type": "BTC-SegWit", "address": match})

        for match in _ETH.findall(text):
            if match not in seen:
                seen.add(match)
                wallets.append({"type": "ETH", "address": match})

        return wallets

    @staticmethod
    def _extract_pgp(text: str) -> List[str]:
        """Find PGP public key blocks (returns list of full blocks)."""
        return _PGP_BLOCK.findall(text)

    @staticmethod
    def _extract_emails(text: str) -> List[str]:
        """Find unique email addresses."""
        return list(set(_EMAIL.findall(text)))

    @staticmethod
    def _extract_onion_links(text: str, source_url: str = "") -> List[str]:
        """Find .onion URLs / hostnames, excluding the source URL itself."""
        links: set = set()

        for match in _ONION_URL.findall(text):
            links.add(match.rstrip("/"))

        for match in _ONION_HOST.findall(text):
            full = f"http://{match}"
            links.add(full)

        # Remove the source URL so we only report *other* onion links
        source_host = ""
        if source_url:
            try:
                source_host = source_url.split("//")[-1].split("/")[0]
            except Exception:
                pass

        return sorted(
            link for link in links
            if source_host and source_host not in link or not source_host
        )

    # ------------------------------------------------------------------
    # LLM analysis
    # ------------------------------------------------------------------

    def _analyze_with_llm(self, text: str) -> Dict[str, Any]:
        """
        Send truncated page text to an OpenAI-compatible API and return
        structured analysis (summary, legitimacy, category).
        """
        empty = {
            "summary": None,
            "legitimacy_score": None,
            "legitimacy_reason": None,
            "category": None,
        }

        if not self.llm_api_key:
            return empty

        # Smart truncation: prefer the first N chars (header/nav area is
        # typically the most informative part of a page).
        truncated = text[:_LLM_MAX_CHARS]
        if len(text) > _LLM_MAX_CHARS:
            truncated += "\n\n[...content truncated...]"

        try:
            import openai

            client = openai.OpenAI(api_key=self.llm_api_key)
            response = client.chat.completions.create(
                model=self.llm_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": truncated},
                ],
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)

            return {
                "summary": data.get("summary"),
                "legitimacy_score": data.get("legitimacy_score"),
                "legitimacy_reason": data.get("legitimacy_reason"),
                "category": data.get("category"),
            }

        except ImportError:
            logger.warning("openai package not installed — skipping LLM analysis")
            return empty
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            return empty

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        return {
            "crypto_wallets": [],
            "pgp_keys": [],
            "emails": [],
            "onion_links": [],
            "llm_summary": None,
            "llm_legitimacy_score": None,
            "llm_legitimacy_reason": None,
            "llm_category": None,
            "total_entities": 0,
        }
