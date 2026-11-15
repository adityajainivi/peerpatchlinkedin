"""Turn LinkedIn post IDs and "2d"-style labels into times."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_URN_ID = re.compile(r"urn:li:(?:activity|share|ugcPost):(\d{15,20})")
_EARLIEST_MS = 1_262_304_000_000  # 2010-01-01
_LATEST_MS = 4_102_444_800_000  # 2100-01-01

_SHORT = re.compile(r"^\s*(\d+)\s*(mo|yr|s|m|h|d|w|y)\b", re.IGNORECASE)
_LONG = re.compile(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE)
_HOURS = {
    "s": 1 / 3600, "second": 1 / 3600,
    "m": 1 / 60, "minute": 1 / 60,
    "h": 1.0, "hour": 1.0,
    "d": 24.0, "day": 24.0,
    "w": 168.0, "week": 168.0,
    "mo": 720.0, "month": 720.0,
    "y": 8760.0, "yr": 8760.0, "year": 8760.0,
}


def urn_to_datetime(urn: str) -> datetime | None:
    """LinkedIn post IDs keep the creation time (ms since 1970) in their top 41 bits."""
    match = _URN_ID.search(urn or "")
    if not match:
        return None
    ms = int(match.group(1)) >> 22
    if not _EARLIEST_MS <= ms <= _LATEST_MS:
        return None
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc) + timedelta(milliseconds=ms % 1000)


def relative_label_to_hours(label: str) -> float | None:
    """'5h', '1d • Edited', '2 weeks ago', 'now' -> hours. None if it can't tell."""
    text = (label or "").strip().lower()
    if not text:
        return None
    if text.startswith("now") or "just now" in text:
        return 0.0
    match = _LONG.search(text) or _SHORT.match(text)
    if not match:
        return None
    return int(match.group(1)) * _HOURS[match.group(2).lower()]
