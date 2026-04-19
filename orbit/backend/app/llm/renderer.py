"""ORBIT renderer module — verdict text rendering via Gemini LLM."""

from __future__ import annotations

import asyncio
import logging
import re

from app.config import Settings
from app.schemas import DirectionEnum, VerdictClass, VerdictObject

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LLM_TIMEOUT: float = 15.0

_BLACKLISTED_WORDS: tuple[str, ...] = (
    "significant",
    "substantial",
    "likely",
    "probably",
    "may",
    "could",
    "potentially",
    "suggests",
    "expected to",
    "will",
)

# Pre-compile a single regex matching any blacklisted word (case-insensitive).
# Use word boundaries for single-word entries; phrase entries match as-is.
_BLACKLIST_PATTERN: re.Pattern[str] = re.compile(
    "|".join(rf"\b{re.escape(w)}\b" if " " not in w else re.escape(w) for w in _BLACKLISTED_WORDS),
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Direction arrow helper
# ---------------------------------------------------------------------------

_DIRECTION_ARROWS: dict[DirectionEnum, str] = {
    DirectionEnum.LONG: "^",
    DirectionEnum.SHORT: "v",
    DirectionEnum.FLAT: "-",
}


def _direction_arrow(direction: DirectionEnum) -> str:
    return _DIRECTION_ARROWS.get(direction, "-")


# ---------------------------------------------------------------------------
# Deterministic template rendering (no LLM)
# ---------------------------------------------------------------------------

_ACT_TEMPLATE = (
    "[{verdict_class} {direction_arrow} {ticker}]  EVENT {description} {time}"
    " · SCORE {score} · EXPOSURE {code} {weight}%\n"
    "MOVE {low}% to {high}% / {horizon} · n={n} · HIT {rate}%"
)

_WAIT_TEMPLATE = "[WAIT — {ticker}]  {reason}"

_IGNORE_TEMPLATE = "[IGNORE — {ticker}]  no material events above 0.30 relevance"


def _render_deterministic(verdict: VerdictObject) -> str:
    """Fill slot templates directly from the VerdictObject — no LLM."""
    meta = verdict.verdict_object

    if verdict.verdict_class == VerdictClass.HOLD:
        reason = meta.get("reason", "insufficient signal")
        return _WAIT_TEMPLATE.format(ticker=verdict.ticker, reason=reason)

    # Check low relevance -> IGNORE
    if verdict.relevance_score < 0.30:
        return _IGNORE_TEMPLATE.format(ticker=verdict.ticker)

    # ACT path
    return _ACT_TEMPLATE.format(
        verdict_class=verdict.verdict_class.value.upper(),
        direction_arrow=_direction_arrow(verdict.direction),
        ticker=verdict.ticker,
        description=meta.get("description", "—"),
        time=meta.get("time", "—"),
        score=f"{verdict.relevance_score:.2f}",
        code=meta.get("code", "—"),
        weight=meta.get("weight", "0"),
        low=meta.get("low", "0"),
        high=meta.get("high", "0"),
        horizon=meta.get("horizon", "—"),
        n=meta.get("n", "0"),
        rate=meta.get("rate", "0"),
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a verdict renderer for a trading intelligence dashboard called ORBIT.
Given the structured verdict data below, render a human-readable verdict string.

RULES:
- Use the EXACT template format below (fill the slots).
- Do NOT use any of these words: significant, substantial, likely, probably, \
may, could, potentially, suggests, expected to, will.
- Be terse and factual.

TEMPLATES:
ACT: "[{{verdict_class}} {{direction_arrow}} {{ticker}}]  EVENT {{description}} {{time}} \
· SCORE {{score}} · EXPOSURE {{code}} {{weight}}%\\nMOVE {{low}}% to {{high}}% / \
{{horizon}} · n={{n}} · HIT {{rate}}%"
WAIT: "[WAIT — {{ticker}}]  {{reason}}"
IGNORE: "[IGNORE — {{ticker}}]  no material events above 0.30 relevance"

VERDICT DATA:
ticker: {ticker}
verdict_class: {verdict_class}
direction: {direction}
relevance_score: {relevance_score}
metadata: {metadata}

Respond with ONLY the rendered verdict string. No quotes, no markdown, no explanation.
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


def _has_blacklisted_words(text: str) -> bool:
    """Return True if text contains any blacklisted word."""
    return bool(_BLACKLIST_PATTERN.search(text))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def render_verdict(verdict: VerdictObject, settings: Settings) -> str:
    """Render a human-readable verdict string via Gemini LLM.

    Rejects and retries once if output contains blacklisted words.
    Falls back to deterministic template on second failure.
    """
    prompt = _PROMPT_TEMPLATE.format(
        ticker=verdict.ticker,
        verdict_class=verdict.verdict_class.value,
        direction=verdict.direction.value,
        relevance_score=verdict.relevance_score,
        metadata=verdict.verdict_object,
    )

    loop = asyncio.get_running_loop()

    for attempt in range(2):
        try:
            raw_text: str = await asyncio.wait_for(
                loop.run_in_executor(None, _call_gemini_sync, prompt, settings.gemini_api_key),
                timeout=_LLM_TIMEOUT,
            )
            cleaned = raw_text.strip()
            if _has_blacklisted_words(cleaned):
                logger.warning(
                    "Renderer attempt %d: blacklisted word found, %s",
                    attempt + 1,
                    "retrying" if attempt == 0 else "falling back to deterministic",
                )
                if attempt == 0:
                    continue
                return _render_deterministic(verdict)
            return cleaned
        except Exception:
            if attempt == 0:
                logger.warning("Renderer attempt %d failed, retrying", attempt + 1)
                continue
            logger.warning("Renderer retry failed, returning deterministic template")

    return _render_deterministic(verdict)
