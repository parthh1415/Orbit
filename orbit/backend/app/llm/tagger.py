"""ORBIT tagger module — news sentiment tagging via Gemini LLM."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class TagResult(BaseModel):
    """Structured sentiment tag for a news article."""

    model_config = ConfigDict(strict=True, frozen=True)

    sentiment: Literal["positive", "negative", "neutral"]
    countries_affected: list[str]
    sectors_affected: list[str]
    magnitude: Literal["high", "medium", "low"]
    confidence: Literal["high", "medium", "low"]


# ---------------------------------------------------------------------------
# In-memory cache keyed by SHA-256 of headline+snippet
# ---------------------------------------------------------------------------

_cache: dict[str, TagResult] = {}

_LLM_TIMEOUT: float = 15.0

# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

_FALLBACK = TagResult(
    sentiment="neutral",
    countries_affected=[],
    sectors_affected=[],
    magnitude="low",
    confidence="low",
)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a geopolitical news tagger. Given the following news headline and snippet, \
produce a JSON object with these exact keys:

- "sentiment": one of "positive", "negative", "neutral"
- "countries_affected": list of ISO 3166-1 alpha-2 country codes (e.g. ["US", "CN"])
- "sectors_affected": list of sector strings (e.g. ["technology", "energy"])
- "magnitude": one of "high", "medium", "low"
- "confidence": one of "high", "medium", "low"

Respond with ONLY valid JSON. No markdown, no explanation.

Headline: {headline}
Snippet: {snippet}
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _content_hash(headline: str, snippet: str) -> str:
    """Return SHA-256 hex digest for the given headline+snippet."""
    return hashlib.sha256((headline + snippet).encode("utf-8")).hexdigest()


def _call_gemini_sync(prompt: str, api_key: str) -> str:
    """Synchronous Gemini call — to be wrapped in asyncio executor."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]  # SDK lacks __all__
    model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore[attr-defined]  # SDK lacks __all__
    response = model.generate_content(prompt)
    return response.text  # type: ignore[no-any-return]  # SDK untyped


def _parse_tag_json(raw: str) -> TagResult:
    """Parse raw LLM text into a TagResult; raises on any mismatch."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data: dict[str, object] = json.loads(text)
    return TagResult.model_validate(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def tag_article(headline: str, snippet: str, settings: Settings) -> TagResult:
    """Tag a news article with sentiment, countries, sectors, magnitude, confidence.

    Uses an in-memory cache keyed by SHA-256(headline+snippet).
    On parse failure retries once, then returns deterministic fallback.
    """
    cache_key = _content_hash(headline, snippet)
    if cache_key in _cache:
        return _cache[cache_key]

    prompt = _PROMPT_TEMPLATE.format(headline=headline, snippet=snippet)
    loop = asyncio.get_running_loop()

    for attempt in range(2):
        try:
            raw_text: str = await asyncio.wait_for(
                loop.run_in_executor(None, _call_gemini_sync, prompt, settings.gemini_api_key),
                timeout=_LLM_TIMEOUT,
            )
            result = _parse_tag_json(raw_text)
            _cache[cache_key] = result
            return result
        except Exception:
            if attempt == 0:
                logger.warning("Tagger attempt %d failed, retrying", attempt + 1)
                continue
            logger.warning("Tagger retry failed, returning deterministic fallback")

    _cache[cache_key] = _FALLBACK
    return _FALLBACK
