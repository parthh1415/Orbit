"""ORBIT parser module — command bar intent parsing via Gemini LLM."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ParseResult(BaseModel):
    """Parsed intent from a user command-bar query."""

    model_config = ConfigDict(strict=True, frozen=True)

    intent: Literal["focus", "filter", "recall", "query", "unknown"]
    target_ticker: str | None
    filters: dict[str, str]
    entities: list[str]
    confidence: float


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LLM_TIMEOUT: float = 15.0

_FALLBACK_UNKNOWN = ParseResult(
    intent="unknown",
    target_ticker=None,
    filters={},
    entities=[],
    confidence=0.0,
)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a command-bar parser for a trading intelligence dashboard called ORBIT.
Given the user query, extract the structured intent.

Return ONLY valid JSON with these exact keys:
- "intent": one of "focus", "filter", "recall", "query", "unknown"
  - "focus" = user wants to zoom in on a specific ticker
  - "filter" = user wants to filter events by criteria
  - "recall" = user wants to recall past events or trades
  - "query" = user asks a general analytical question
  - "unknown" = cannot determine intent
- "target_ticker": string ticker symbol or null
- "filters": object mapping filter keys to values (e.g. {{"sector": "tech"}})
- "entities": list of entity strings mentioned (tickers, countries, sectors)
- "confidence": float 0.0-1.0

Respond with ONLY valid JSON. No markdown, no explanation.

User query: {query}
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _call_gemini_sync(prompt: str, api_key: str) -> str:
    """Synchronous Gemini call — to be wrapped in asyncio executor."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)  # type: ignore[attr-defined]  # SDK lacks __all__
    model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore[attr-defined]  # SDK lacks __all__
    response = model.generate_content(prompt)
    return response.text  # type: ignore[no-any-return]  # SDK untyped


def _parse_result_json(raw: str) -> ParseResult:
    """Parse raw LLM text into a ParseResult; raises on any mismatch."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data: dict[str, object] = json.loads(text)
    return ParseResult.model_validate(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def parse_command(query: str, settings: Settings) -> ParseResult:
    """Parse a user command-bar query into structured intent.

    On failure retries once, then returns intent='unknown' fallback.
    """
    prompt = _PROMPT_TEMPLATE.format(query=query)
    loop = asyncio.get_running_loop()

    for attempt in range(2):
        try:
            raw_text: str = await asyncio.wait_for(
                loop.run_in_executor(None, _call_gemini_sync, prompt, settings.gemini_api_key),
                timeout=_LLM_TIMEOUT,
            )
            result = _parse_result_json(raw_text)
            return result
        except Exception:
            if attempt == 0:
                logger.warning("Parser attempt %d failed, retrying", attempt + 1)
                continue
            logger.warning("Parser retry failed, returning unknown fallback")

    return _FALLBACK_UNKNOWN
