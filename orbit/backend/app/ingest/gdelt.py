"""ORBIT GDELT ingestion — polls GDELT GKG/events feed every 15 min."""

from __future__ import annotations

import csv
import io
import json
import logging
import pathlib
import uuid
import zipfile
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.db import get_db
from app.ingest._demo_time import rebase_event_timestamp

logger = logging.getLogger(__name__)

_LASTUPDATE_URL = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"

# Columns in GDELT v2 events export TSV (58 fields).
# We only use a handful; map by index.
_COL_GLOBAL_EVENT_ID = 0
_COL_DAY = 1
_COL_ACTOR1_NAME = 5
_COL_ACTOR1_COUNTRY = 7
_COL_ACTOR2_NAME = 15
_COL_ACTOR2_COUNTRY = 17
_COL_EVENT_CODE = 26
_COL_GOLDSTEIN = 30
_COL_NUM_SOURCES = 31
_COL_NUM_ARTICLES = 32
_COL_ACTION_GEO_FULLNAME = 49
_COL_ACTION_GEO_LAT = 53
_COL_ACTION_GEO_LON = 54
_COL_SOURCEURL = 57

# Top-level CAMEO verb descriptions (first two digits of the event code).
_CAMEO_VERBS: dict[str, str] = {
    "01": "made a public statement about",
    "02": "appealed to",
    "03": "expressed intent to cooperate with",
    "04": "consulted with",
    "05": "engaged diplomatically with",
    "06": "provided material cooperation to",
    "07": "provided aid to",
    "08": "made concessions to",
    "09": "investigated activities of",
    "10": "demanded action from",
    "11": "disapproved of",
    "12": "rejected proposals from",
    "13": "threatened",
    "14": "protested against",
    "15": "exhibited force posture toward",
    "16": "reduced relations with",
    "17": "imposed sanctions on",
    "18": "used force against",
    "19": "engaged in armed conflict with",
    "20": "engaged in mass violence in",
}

_DEMO_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "data" / "demo_snapshot.json"


def build_gdelt_description(
    actor1: str,
    actor2: str,
    cameo_code: str,
    geo_fullname: str,
) -> str:
    """Build a human-readable event description from GDELT fields.

    Returns a string like ``"UNITED STATES imposed sanctions on CHINA in Taiwan"``
    or a shorter form when some fields are missing.
    """
    verb_key = cameo_code[:2] if len(cameo_code) >= 2 else ""
    verb = _CAMEO_VERBS.get(verb_key, "")

    parts: list[str] = []
    if actor1:
        parts.append(actor1)
    if verb:
        parts.append(verb)
    if actor2:
        parts.append(actor2)
    if geo_fullname:
        parts.append(f"in {geo_fullname}")

    if parts:
        return " ".join(parts)
    return ""


def _safe_float(val: str, default: float = 0.0) -> float:
    """Parse a float, returning *default* on failure."""
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: str, default: int = 0) -> int:
    """Parse an int, returning *default* on failure."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def parse_gdelt_rows(
    tsv_text: str,
) -> list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]]:
    """Parse GDELT TSV text into row tuples for the events table.

    Returns a list of tuples:
        (id, source, timestamp, description, cameo_code, goldstein_score,
         num_sources, lat, lon, countries, sentiment, metadata)
    """
    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    for fields in reader:
        if len(fields) < 58:
            continue
        event_id = fields[_COL_GLOBAL_EVENT_ID].strip()
        if not event_id:
            continue

        day_str = fields[_COL_DAY].strip()
        try:
            ts = datetime.strptime(day_str[:8], "%Y%m%d").replace(tzinfo=UTC)
        except (ValueError, IndexError):
            ts = datetime.now(tz=UTC)

        cameo = fields[_COL_EVENT_CODE].strip()
        goldstein = _safe_float(fields[_COL_GOLDSTEIN])
        num_sources = _safe_int(fields[_COL_NUM_SOURCES], 1)
        lat = _safe_float(fields[_COL_ACTION_GEO_LAT])
        lon = _safe_float(fields[_COL_ACTION_GEO_LON])

        actor1_name = fields[_COL_ACTOR1_NAME].strip()
        actor1_country = fields[_COL_ACTOR1_COUNTRY].strip()
        actor2_name = fields[_COL_ACTOR2_NAME].strip()
        actor2_country = fields[_COL_ACTOR2_COUNTRY].strip()
        geo_fullname = fields[_COL_ACTION_GEO_FULLNAME].strip()

        countries_list: list[str] = []
        if actor1_country:
            countries_list.append(actor1_country)
        if actor2_country and actor2_country != actor1_country:
            countries_list.append(actor2_country)

        description = build_gdelt_description(
            actor1=actor1_name or actor1_country,
            actor2=actor2_name or actor2_country,
            cameo_code=cameo,
            geo_fullname=geo_fullname,
        )
        if not description:
            description = f"GDELT event {event_id}"
        db_id = f"gdelt-{event_id}"

        rows.append(
            (
                db_id,
                "gdelt",
                ts.isoformat(),
                description,
                cameo,
                goldstein,
                num_sources,
                lat,
                lon,
                json.dumps(countries_list),
                0.0,
                "{}",
            )
        )
    return rows


async def _fetch_latest_export_url(client: httpx.AsyncClient) -> str | None:
    """Fetch the GDELT lastupdate.txt and return the events export URL."""
    resp = await client.get(_LASTUPDATE_URL, timeout=10.0)
    resp.raise_for_status()
    for line in resp.text.strip().splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[2].endswith(".export.CSV.zip"):
            return parts[2]
    return None


async def _download_and_extract(client: httpx.AsyncClient, url: str) -> str:
    """Download a GDELT zip and return the CSV text inside it."""
    resp = await client.get(url, timeout=30.0)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if name.endswith(".CSV"):
                return zf.read(name).decode("utf-8", errors="replace")
    return ""


async def _ingest_demo(settings: Settings) -> int:
    """Load demo events from demo_snapshot.json."""
    if not _DEMO_PATH.exists():
        logger.warning("Demo snapshot not found at %s", _DEMO_PATH)
        return 0

    raw = _DEMO_PATH.read_text(encoding="utf-8")
    data: dict[str, object] = json.loads(raw)
    events = data.get("events")
    if not isinstance(events, list):
        return 0

    now = datetime.now(tz=UTC)
    rows: list[tuple[str, str, str, str, str, float, int, float, float, str, float, str]] = []
    for evt in events:
        if not isinstance(evt, dict):
            continue
        event_id = str(evt.get("id", uuid.uuid4().hex))
        rows.append(
            (
                event_id,
                str(evt.get("source", "gdelt")),
                rebase_event_timestamp(event_id, now),
                str(evt.get("description", "")),
                str(evt.get("cameo_code", "")),
                float(evt.get("goldstein_score", 0.0)),
                int(evt.get("num_sources", 1)),
                float(evt.get("lat", 0.0)),
                float(evt.get("lon", 0.0)),
                str(evt.get("countries", "[]")),
                float(evt.get("sentiment", 0.0)),
                str(evt.get("metadata", "{}")),
            )
        )

    if not rows:
        return 0

    async with get_db(settings.database_url) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO events
               (id, source, timestamp, description, cameo_code,
                goldstein_score, num_sources, lat, lon,
                countries, sentiment, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        await db.commit()

    return len(rows)


async def poll_gdelt(settings: Settings) -> int:
    """Poll GDELT for the latest events export.

    Returns the number of new rows written.
    """
    if settings.demo_mode:
        return await _ingest_demo(settings)

    try:
        async with httpx.AsyncClient() as client:
            export_url = await _fetch_latest_export_url(client)
            if export_url is None:
                logger.warning("No GDELT export URL found in lastupdate.txt")
                return 0

            tsv_text = await _download_and_extract(client, export_url)
            if not tsv_text:
                logger.warning("Empty GDELT export CSV")
                return 0

            rows = parse_gdelt_rows(tsv_text)
            if not rows:
                return 0

            async with get_db(settings.database_url) as db:
                await db.executemany(
                    """INSERT OR IGNORE INTO events
                       (id, source, timestamp, description, cameo_code,
                        goldstein_score, num_sources, lat, lon,
                        countries, sentiment, metadata)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
                await db.commit()

            logger.info("GDELT: ingested %d events", len(rows))
            return len(rows)

    except httpx.HTTPError as exc:
        logger.error("GDELT HTTP error: %s", exc)
        return 0
    except Exception:
        logger.exception("GDELT unexpected error")
        return 0
