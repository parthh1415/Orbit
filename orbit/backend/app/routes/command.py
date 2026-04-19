"""ORBIT command routes — simple keyword parser for the command terminal."""

from __future__ import annotations

import re

from fastapi import APIRouter

from app.schemas import CommandRequest, CommandResponse

router = APIRouter(prefix="/api/command", tags=["command"])

# ---------------------------------------------------------------------------
# Simple keyword patterns — accept both "focus AAPL" and "focus:AAPL" forms.
# (LLM parser wired in Phase 5)
# ---------------------------------------------------------------------------

_FOCUS_RE = re.compile(r"^focus[\s:](\w+)$", re.IGNORECASE)
_FILTER_RE = re.compile(r"^filter[\s:](\w+)$", re.IGNORECASE)


def _parse_command(raw: str) -> tuple[bool, str]:
    """Parse a command string and return ``(success, output)``."""
    text = raw.strip()
    if not text:
        return False, "UNKNOWN COMMAND \u00b7 TYPE HELP FOR OPTIONS"

    upper = text.upper()

    # focus <ticker>
    focus_match = _FOCUS_RE.match(text)
    if focus_match:
        ticker = focus_match.group(1).upper()
        return True, f"FOCUSED ON {ticker}"

    # filter <country>
    filter_match = _FILTER_RE.match(text)
    if filter_match:
        country = filter_match.group(1).upper()
        return True, f"FILTERED EVENTS TO {country} \u00b7 3 MATCHES"

    # status
    if upper == "STATUS":
        return True, "ALL FEEDS ACTIVE \u00b7 4 SOURCES \u00b7 8 EVENTS \u00b7 3 TICKERS"

    # ports
    if upper == "PORTS":
        return (
            True,
            "5 PORTS TRACKED \u00b7 SINGAPORE 342 \u00b7 SHANGHAI 456 \u00b7 ROTTERDAM 187",
        )

    # flights
    if upper == "FLIGHTS":
        return (
            True,
            "13 CORRIDORS ACTIVE \u00b7 8 ROUTES \u00b7 SEMICONDUCTOR/COMPONENTS/FINISHED GOODS",
        )

    # help
    if upper == "HELP":
        return (
            True,
            "COMMANDS: FOCUS <TICKER> | FILTER <COUNTRY> | STATUS | PORTS | FLIGHTS | HELP",
        )

    return False, "UNKNOWN COMMAND \u00b7 TYPE HELP FOR OPTIONS"


@router.post("/parse", response_model=CommandResponse)
async def parse_command(body: CommandRequest) -> CommandResponse:
    """Parse a command string and return a structured response."""
    success, output = _parse_command(body.command)
    return CommandResponse(success=success, output=output)
