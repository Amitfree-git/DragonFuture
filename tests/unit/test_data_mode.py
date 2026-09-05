from datetime import datetime, timezone

import pytest

from dragonboat_ai.futures_agent.domain.data_mode import (
    DataMode,
    NaiveTimestampError,
    available_at_for_mode,
    is_strict_pit,
    require_aware_utc,
)


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(NaiveTimestampError):
        require_aware_utc(datetime(2026, 9, 4, 16, 0))


def test_live_capture_available_at_not_before_received_at() -> None:
    published = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)
    received = datetime(2026, 9, 4, 8, 30, tzinfo=timezone.utc)
    available = available_at_for_mode(
        DataMode.LIVE_CAPTURE,
        published_at=published,
        received_at=received,
    )
    assert available == received
    assert available >= received


def test_historical_vintage_uses_published_at() -> None:
    published = datetime(2026, 9, 4, 7, 0, tzinfo=timezone.utc)
    received = datetime(2026, 9, 10, 1, 0, tzinfo=timezone.utc)
    available = available_at_for_mode(
        DataMode.HISTORICAL_VINTAGE,
        published_at=published,
        received_at=received,
    )
    assert available == published


def test_historical_vintage_without_publication_is_not_invented() -> None:
    received = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        available_at_for_mode(
            DataMode.HISTORICAL_VINTAGE,
            published_at=None,
            received_at=received,
        )


def test_estimated_mode_not_strict_pit() -> None:
    assert is_strict_pit(DataMode.ESTIMATED) is False
    assert is_strict_pit(DataMode.FINAL_ONLY) is False
    assert is_strict_pit(DataMode.LIVE_CAPTURE) is True
    assert is_strict_pit(DataMode.HISTORICAL_VINTAGE) is True
