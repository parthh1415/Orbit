"""ORBIT configuration — loads env vars with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Tickers tracked by ORBIT.
TRACKED_TICKERS: tuple[str, ...] = ("AAPL", "NVDA", "TSM")


def _env(key: str, default: str = "") -> str:
    """Read an environment variable with a fallback.

    Strips leading/trailing whitespace so that copy-paste artefacts in
    shell exports (e.g. ``export ALPACA_API_KEY=" KEY "``) never cause
    silent authentication failures.
    """
    return os.environ.get(key, default).strip()


@dataclass(frozen=True, slots=True)
class Settings:
    """Application-wide settings populated from environment variables."""

    demo_mode: bool = field(default=False)
    replay_mode: bool = field(default=False)
    replay_date: str = field(default="2026-04-16")
    replay_speed: int = field(default=60)
    alpaca_api_key: str = field(default="")
    alpaca_secret_key: str = field(default="")
    newsapi_key: str = field(default="")
    gemini_api_key: str = field(default="")
    database_url: str = field(default="data/orbit.db")

    @classmethod
    def from_env(cls) -> Settings:
        """Construct settings from environment variables."""
        replay_speed_raw = _env("ORBIT_REPLAY_SPEED", "60")
        try:
            replay_speed = int(replay_speed_raw)
        except ValueError:
            replay_speed = 60
        return cls(
            demo_mode=_env("ORBIT_DEMO_MODE", "0") not in ("0", "false", ""),
            replay_mode=_env("ORBIT_REPLAY_MODE", "0") not in ("0", "false", ""),
            replay_date=_env("ORBIT_REPLAY_DATE", "2026-04-16"),
            replay_speed=replay_speed,
            alpaca_api_key=_env("ALPACA_API_KEY", ""),
            alpaca_secret_key=_env("ALPACA_SECRET_KEY", ""),
            newsapi_key=_env("NEWSAPI_KEY", ""),
            gemini_api_key=_env("GEMINI_API_KEY", ""),
            database_url=_env("DATABASE_URL", "data/orbit.db"),
        )


def get_settings() -> Settings:
    """Return a singleton-style Settings (re-reads env each call)."""
    return Settings.from_env()
