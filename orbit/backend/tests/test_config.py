"""Tests for app.config."""

from __future__ import annotations

import os
from unittest import mock

from app.config import TRACKED_TICKERS, Settings, get_settings


def test_tracked_tickers() -> None:
    """Verify the tracked ticker list."""
    assert TRACKED_TICKERS == ("AAPL", "NVDA", "TSM")


def test_defaults() -> None:
    """Settings.from_env picks up defaults when env is empty."""
    settings = Settings.from_env()
    assert settings.demo_mode is False
    assert settings.database_url == "data/orbit.db"
    # API keys default to empty (set via env vars, not hardcoded)
    assert isinstance(settings.alpaca_api_key, str)
    assert isinstance(settings.alpaca_secret_key, str)
    assert isinstance(settings.newsapi_key, str)
    assert isinstance(settings.gemini_api_key, str)


def test_demo_mode_from_env() -> None:
    """ORBIT_DEMO_MODE=1 flips demo_mode to True."""
    with mock.patch.dict(os.environ, {"ORBIT_DEMO_MODE": "1"}):
        settings = Settings.from_env()
        assert settings.demo_mode is True


def test_demo_mode_false_variants() -> None:
    """0, false, and empty all mean demo_mode=False."""
    for val in ("0", "false", ""):
        with mock.patch.dict(os.environ, {"ORBIT_DEMO_MODE": val}):
            settings = Settings.from_env()
            assert settings.demo_mode is False, f"Expected False for {val!r}"


def test_database_url_override() -> None:
    """DATABASE_URL env var overrides the default."""
    with mock.patch.dict(os.environ, {"DATABASE_URL": "/tmp/test.db"}):
        settings = Settings.from_env()
        assert settings.database_url == "/tmp/test.db"


def test_get_settings_returns_settings() -> None:
    """get_settings() returns a Settings instance."""
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_settings_frozen() -> None:
    """Settings is frozen — assignment raises."""
    settings = get_settings()
    raised = False
    try:
        settings.demo_mode = True  # type: ignore[misc]
    except AttributeError:
        raised = True
    assert raised
