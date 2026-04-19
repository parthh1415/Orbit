"""Rebase demo snapshot timestamps so events appear recent."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# Minutes-ago offsets for each demo event, keyed by event id.
_EVENT_OFFSETS: dict[str, int] = {
    "demo-gdelt-001": 10,
    "demo-gdelt-002": 25,
    "demo-gdelt-003": 45,
    "demo-gdelt-004": 30,
    "demo-gdelt-005": 30,
    "demo-gdelt-006": 30,
    "demo-gdelt-007": 30,
    "demo-gdelt-008": 30,
    "demo-news-001": 5,
    "demo-news-002": 15,
    "demo-news-003": 30,
    "demo-news-004": 30,
    "demo-fred-001": 60,
    "demo-fred-002": 120,
}

# Default offset (in minutes) for events not explicitly listed.
_DEFAULT_OFFSET: int = 30


def rebase_event_timestamp(event_id: str, now: datetime | None = None) -> str:
    """Return an ISO-8601 timestamp that is *recent* for the given event.

    Uses a fixed per-event offset so the relative ordering stays stable.
    """
    if now is None:
        now = datetime.now(tz=UTC)
    minutes = _EVENT_OFFSETS.get(event_id, _DEFAULT_OFFSET)
    return (now - timedelta(minutes=minutes)).isoformat()


def rebase_score_timestamp(event_id: str, now: datetime | None = None) -> str:
    """Return a ``computed_at`` timestamp 1 minute after the event's rebased time."""
    if now is None:
        now = datetime.now(tz=UTC)
    minutes = _EVENT_OFFSETS.get(event_id, _DEFAULT_OFFSET)
    return (now - timedelta(minutes=minutes) + timedelta(minutes=1)).isoformat()


def rebase_port_timestamp(now: datetime | None = None) -> str:
    """Return a timestamp ~10 minutes ago for port snapshots."""
    if now is None:
        now = datetime.now(tz=UTC)
    return (now - timedelta(minutes=10)).isoformat()


def rebase_bar_timestamp(index: int, now: datetime | None = None) -> str:
    """Return a timestamp for bar *index* (0-based), each 1 minute apart.

    Index 0 is the oldest bar; higher indices are more recent.
    """
    if now is None:
        now = datetime.now(tz=UTC)
    # 15 bars total in the snapshot — space them 1 min apart ending ~1 min ago.
    offset = max(15 - index, 1)
    return (now - timedelta(minutes=offset)).isoformat()
