from datetime import date, datetime, timezone

import pytest

from dragonboat_ai.futures_agent.infrastructure.database.calendar_store import SqlAlchemyCalendarStore


@pytest.mark.point_in_time
def test_calendar_revision_point_in_time(database) -> None:
    store = SqlAlchemyCalendarStore(database["session_factory"])
    store.add_day(
        exchange="SHFE",
        version="cal_v1",
        trading_date=date(2026, 1, 1),
        is_trading_day=True,
        available_at=datetime(2025, 12, 1, 0, 0, tzinfo=timezone.utc),
        revision_no=1,
    )
    store.add_day(
        exchange="SHFE",
        version="cal_v2",
        trading_date=date(2026, 1, 1),
        is_trading_day=False,
        available_at=datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc),
        revision_no=2,
    )
    before = store.is_trading_day(
        exchange="SHFE",
        trading_date=date(2026, 1, 1),
        as_of=datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc),
    )
    after = store.is_trading_day(
        exchange="SHFE",
        trading_date=date(2026, 1, 1),
        as_of=datetime(2026, 1, 11, 8, 0, tzinfo=timezone.utc),
    )
    assert before is True
    assert after is False
