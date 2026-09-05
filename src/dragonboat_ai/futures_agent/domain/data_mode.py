from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum


class NaiveTimestampError(ValueError):
    """Raised when a timestamp is naive or has an unspecified UTC offset."""


class DataMode(str, Enum):
    LIVE_CAPTURE = "live_capture"
    HISTORICAL_VINTAGE = "historical_vintage"
    FINAL_ONLY = "final_only"
    ESTIMATED = "estimated"


STRICT_PIT_MODES = {DataMode.LIVE_CAPTURE, DataMode.HISTORICAL_VINTAGE}


def is_strict_pit(mode: DataMode) -> bool:
    return mode in STRICT_PIT_MODES


def require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveTimestampError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


def available_at_for_mode(
    mode: DataMode,
    *,
    published_at: datetime | None,
    received_at: datetime,
    estimated_published_at: datetime | None = None,
) -> datetime:
    received = require_aware_utc(received_at)
    if mode is DataMode.LIVE_CAPTURE:
        if published_at is None:
            raise ValueError("live_capture requires published_at")
        published = require_aware_utc(published_at)
        return received if received >= published else published
    if mode is DataMode.HISTORICAL_VINTAGE:
        if published_at is None:
            raise ValueError("historical_vintage requires a verifiable published_at; do not invent one")
        return require_aware_utc(published_at)
    if mode is DataMode.FINAL_ONLY:
        if published_at is not None:
            return require_aware_utc(published_at)
        return received
    if mode is DataMode.ESTIMATED:
        stamp = estimated_published_at or published_at
        if stamp is None:
            raise ValueError("estimated mode requires an explicit estimated or published timestamp")
        return require_aware_utc(stamp)
    raise ValueError(f"unsupported data mode: {mode}")
