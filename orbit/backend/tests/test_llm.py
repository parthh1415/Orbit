"""Tests for app.llm — tagger, parser, renderer (mocked Gemini)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.llm.parser import ParseResult, _parse_result_json, parse_command
from app.llm.renderer import (
    _has_blacklisted_words,
    _render_deterministic,
    render_verdict,
)
from app.llm.tagger import (
    TagResult,
    _cache,
    _content_hash,
    _parse_tag_json,
    tag_article,
)
from app.schemas import DirectionEnum, VerdictClass, VerdictObject

if TYPE_CHECKING:
    pass

NOW = datetime.now(tz=UTC)

_SETTINGS = Settings(gemini_api_key="test-key")


# ---------------------------------------------------------------------------
# TagResult model tests
# ---------------------------------------------------------------------------


class TestTagResult:
    def test_valid_tag(self) -> None:
        tag = TagResult(
            sentiment="positive",
            countries_affected=["US", "CN"],
            sectors_affected=["technology"],
            magnitude="high",
            confidence="high",
        )
        assert tag.sentiment == "positive"
        assert tag.countries_affected == ["US", "CN"]

    def test_frozen(self) -> None:
        tag = TagResult(
            sentiment="neutral",
            countries_affected=[],
            sectors_affected=[],
            magnitude="low",
            confidence="low",
        )
        with pytest.raises(ValidationError):
            tag.sentiment = "positive"


# ---------------------------------------------------------------------------
# ParseResult model tests
# ---------------------------------------------------------------------------


class TestParseResult:
    def test_valid_parse(self) -> None:
        pr = ParseResult(
            intent="focus",
            target_ticker="AAPL",
            filters={"sector": "tech"},
            entities=["AAPL"],
            confidence=0.95,
        )
        assert pr.intent == "focus"
        assert pr.target_ticker == "AAPL"

    def test_unknown_intent(self) -> None:
        pr = ParseResult(
            intent="unknown",
            target_ticker=None,
            filters={},
            entities=[],
            confidence=0.0,
        )
        assert pr.intent == "unknown"
        assert pr.confidence == 0.0


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self) -> None:
        h1 = _content_hash("headline", "snippet")
        h2 = _content_hash("headline", "snippet")
        assert h1 == h2

    def test_different_inputs(self) -> None:
        h1 = _content_hash("a", "b")
        h2 = _content_hash("c", "d")
        assert h1 != h2


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


class TestParseTagJson:
    def test_plain_json(self) -> None:
        raw = json.dumps(
            {
                "sentiment": "negative",
                "countries_affected": ["RU"],
                "sectors_affected": ["energy"],
                "magnitude": "high",
                "confidence": "medium",
            }
        )
        result = _parse_tag_json(raw)
        assert result.sentiment == "negative"
        assert result.countries_affected == ["RU"]

    def test_markdown_fenced_json(self) -> None:
        raw = '```json\n{"sentiment":"neutral","countries_affected":[],"sectors_affected":[],"magnitude":"low","confidence":"low"}\n```'
        result = _parse_tag_json(raw)
        assert result.sentiment == "neutral"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, ValidationError)):
            _parse_tag_json("not json at all")


class TestParseResultJson:
    def test_plain_json(self) -> None:
        raw = json.dumps(
            {
                "intent": "focus",
                "target_ticker": "NVDA",
                "filters": {},
                "entities": ["NVDA"],
                "confidence": 0.9,
            }
        )
        result = _parse_result_json(raw)
        assert result.intent == "focus"
        assert result.target_ticker == "NVDA"

    def test_invalid_intent_raises(self) -> None:
        raw = json.dumps(
            {
                "intent": "invalid_intent",
                "target_ticker": None,
                "filters": {},
                "entities": [],
                "confidence": 0.0,
            }
        )
        with pytest.raises(ValidationError):
            _parse_result_json(raw)


# ---------------------------------------------------------------------------
# Blacklist enforcement
# ---------------------------------------------------------------------------


class TestBlacklist:
    @pytest.mark.parametrize(
        "word",
        [
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
        ],
    )
    def test_blacklisted_words_detected(self, word: str) -> None:
        text = f"The event is {word} going to impact markets."
        assert _has_blacklisted_words(text) is True

    def test_clean_text_passes(self) -> None:
        text = "[BUY ^ AAPL]  EVENT tariff reduction 2024-01-01 · SCORE 0.85"
        assert _has_blacklisted_words(text) is False

    def test_case_insensitive(self) -> None:
        assert _has_blacklisted_words("This is SIGNIFICANT") is True
        assert _has_blacklisted_words("LIKELY outcome") is True


# ---------------------------------------------------------------------------
# Deterministic renderer
# ---------------------------------------------------------------------------


class TestDeterministicRenderer:
    def test_hold_renders_wait(self) -> None:
        v = VerdictObject(
            id="v1",
            ticker="AAPL",
            verdict_class=VerdictClass.HOLD,
            direction=DirectionEnum.FLAT,
            relevance_score=0.5,
            issued_at=NOW,
            verdict_object={"reason": "mixed signals"},
        )
        result = _render_deterministic(v)
        assert result.startswith("[WAIT")
        assert "AAPL" in result
        assert "mixed signals" in result

    def test_low_relevance_renders_ignore(self) -> None:
        v = VerdictObject(
            id="v2",
            ticker="NVDA",
            verdict_class=VerdictClass.BUY,
            direction=DirectionEnum.LONG,
            relevance_score=0.10,
            issued_at=NOW,
        )
        result = _render_deterministic(v)
        assert result.startswith("[IGNORE")
        assert "NVDA" in result

    def test_act_renders_template(self) -> None:
        v = VerdictObject(
            id="v3",
            ticker="TSM",
            verdict_class=VerdictClass.STRONG_BUY,
            direction=DirectionEnum.LONG,
            relevance_score=0.85,
            issued_at=NOW,
            verdict_object={
                "description": "chip export ban",
                "time": "2024-01-15",
                "code": "SEMI",
                "weight": "35",
                "low": "2",
                "high": "8",
                "horizon": "5d",
                "n": "12",
                "rate": "75",
            },
        )
        result = _render_deterministic(v)
        assert "[STRONG_BUY ^" in result
        assert "TSM" in result
        assert "chip export ban" in result
        assert "0.85" in result
        assert "SEMI" in result


# ---------------------------------------------------------------------------
# Tagger — mocked Gemini
# ---------------------------------------------------------------------------


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Gemini response object."""
    mock_resp = MagicMock()
    mock_resp.text = text
    return mock_resp


class TestTaggerWithMock:
    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        _cache.clear()

    @patch("app.llm.tagger._call_gemini_sync")
    async def test_successful_tag(self, mock_call: MagicMock) -> None:
        mock_call.return_value = json.dumps(
            {
                "sentiment": "negative",
                "countries_affected": ["US", "CN"],
                "sectors_affected": ["technology"],
                "magnitude": "high",
                "confidence": "high",
            }
        )
        result = await tag_article("Trade war", "Tariffs imposed", _SETTINGS)
        assert result.sentiment == "negative"
        assert result.countries_affected == ["US", "CN"]
        mock_call.assert_called_once()

    @patch("app.llm.tagger._call_gemini_sync")
    async def test_cache_hit(self, mock_call: MagicMock) -> None:
        mock_call.return_value = json.dumps(
            {
                "sentiment": "positive",
                "countries_affected": [],
                "sectors_affected": [],
                "magnitude": "low",
                "confidence": "low",
            }
        )
        r1 = await tag_article("same headline", "same snippet", _SETTINGS)
        r2 = await tag_article("same headline", "same snippet", _SETTINGS)
        assert r1 == r2
        # Should only call Gemini once due to cache
        mock_call.assert_called_once()

    @patch("app.llm.tagger._call_gemini_sync")
    async def test_fallback_on_bad_json(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "this is not valid json"
        result = await tag_article("headline", "snippet", _SETTINGS)
        assert result.sentiment == "neutral"
        assert result.countries_affected == []
        assert result.magnitude == "low"
        assert result.confidence == "low"
        # Called twice (retry once)
        assert mock_call.call_count == 2

    @patch("app.llm.tagger._call_gemini_sync")
    async def test_fallback_on_exception(self, mock_call: MagicMock) -> None:
        mock_call.side_effect = RuntimeError("API failure")
        result = await tag_article("headline2", "snippet2", _SETTINGS)
        assert result.sentiment == "neutral"
        assert result.magnitude == "low"
        assert mock_call.call_count == 2


# ---------------------------------------------------------------------------
# Parser — mocked Gemini
# ---------------------------------------------------------------------------


class TestParserWithMock:
    @patch("app.llm.parser._call_gemini_sync")
    async def test_successful_parse(self, mock_call: MagicMock) -> None:
        mock_call.return_value = json.dumps(
            {
                "intent": "focus",
                "target_ticker": "AAPL",
                "filters": {},
                "entities": ["AAPL"],
                "confidence": 0.95,
            }
        )
        result = await parse_command("show me AAPL", _SETTINGS)
        assert result.intent == "focus"
        assert result.target_ticker == "AAPL"

    @patch("app.llm.parser._call_gemini_sync")
    async def test_fallback_on_bad_response(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "garbage output"
        result = await parse_command("nonsense query", _SETTINGS)
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert mock_call.call_count == 2

    @patch("app.llm.parser._call_gemini_sync")
    async def test_fallback_on_timeout(self, mock_call: MagicMock) -> None:
        mock_call.side_effect = TimeoutError("too slow")
        result = await parse_command("what happened", _SETTINGS)
        assert result.intent == "unknown"
        assert mock_call.call_count == 2

    @patch("app.llm.parser._call_gemini_sync")
    async def test_parse_result_validation(self, mock_call: MagicMock) -> None:
        """LLM returns valid JSON but invalid intent value."""
        mock_call.return_value = json.dumps(
            {
                "intent": "bogus",
                "target_ticker": None,
                "filters": {},
                "entities": [],
                "confidence": 0.5,
            }
        )
        result = await parse_command("test", _SETTINGS)
        assert result.intent == "unknown"  # fallback
        assert mock_call.call_count == 2


# ---------------------------------------------------------------------------
# Renderer — mocked Gemini
# ---------------------------------------------------------------------------


class TestRendererWithMock:
    def _make_verdict(
        self,
        verdict_class: VerdictClass = VerdictClass.BUY,
        direction: DirectionEnum = DirectionEnum.LONG,
        relevance: float = 0.8,
        meta: dict[str, str] | None = None,
    ) -> VerdictObject:
        return VerdictObject(
            id="v1",
            ticker="AAPL",
            verdict_class=verdict_class,
            direction=direction,
            relevance_score=relevance,
            issued_at=NOW,
            verdict_object=meta or {},
        )

    @patch("app.llm.renderer._call_gemini_sync")
    async def test_successful_render(self, mock_call: MagicMock) -> None:
        clean_output = "[BUY ^ AAPL]  EVENT tariff cut 2024-01-01 · SCORE 0.80 · EXPOSURE SEMI 35%\nMOVE 2% to 5% / 5d · n=10 · HIT 70%"
        mock_call.return_value = clean_output
        v = self._make_verdict()
        result = await render_verdict(v, _SETTINGS)
        assert result == clean_output
        mock_call.assert_called_once()

    @patch("app.llm.renderer._call_gemini_sync")
    async def test_blacklist_triggers_retry(self, mock_call: MagicMock) -> None:
        bad = "This is a significant move for AAPL"
        good = "[BUY ^ AAPL]  EVENT tariff 2024 · SCORE 0.80"
        mock_call.side_effect = [bad, good]
        v = self._make_verdict()
        result = await render_verdict(v, _SETTINGS)
        assert result == good
        assert mock_call.call_count == 2

    @patch("app.llm.renderer._call_gemini_sync")
    async def test_blacklist_double_fail_deterministic(self, mock_call: MagicMock) -> None:
        bad1 = "The stock will likely rise"
        bad2 = "This could substantially impact earnings"
        mock_call.side_effect = [bad1, bad2]
        v = self._make_verdict(
            meta={
                "description": "tariff cut",
                "time": "2024-01-01",
                "code": "SEMI",
                "weight": "35",
                "low": "2",
                "high": "5",
                "horizon": "5d",
                "n": "10",
                "rate": "70",
            }
        )
        result = await render_verdict(v, _SETTINGS)
        # Should be deterministic template
        assert "[BUY ^" in result
        assert "AAPL" in result
        assert "tariff cut" in result

    @patch("app.llm.renderer._call_gemini_sync")
    async def test_exception_falls_back_to_deterministic(self, mock_call: MagicMock) -> None:
        mock_call.side_effect = RuntimeError("API down")
        v = self._make_verdict(verdict_class=VerdictClass.HOLD)
        result = await render_verdict(v, _SETTINGS)
        assert "[WAIT" in result
        assert "AAPL" in result

    @patch("app.llm.renderer._call_gemini_sync")
    async def test_ignore_for_low_relevance(self, mock_call: MagicMock) -> None:
        mock_call.side_effect = RuntimeError("fail")
        v = self._make_verdict(relevance=0.1)
        result = await render_verdict(v, _SETTINGS)
        assert "[IGNORE" in result
        assert "AAPL" in result
