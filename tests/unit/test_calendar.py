from datetime import datetime
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.contracts.calendar import ExchangeCalendar

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _weekday_calendar() -> ExchangeCalendar:
    return ExchangeCalendar.weekday_sessions(
        exchange="SHFE",
        version="test_weekday_v1",
        night_open="21:00",
        night_close="23:00",
        day_open="09:00",
        day_close="15:00",
    )


def test_night_session_exchange_trading_date() -> None:
    calendar = _weekday_calendar()
    monday_night = datetime(2026, 9, 7, 21, 5, tzinfo=SHANGHAI)
    trading_date = calendar.trading_date_for(monday_night)
    assert trading_date.isoformat() == "2026-09-08"


def test_friday_night_maps_to_next_monday() -> None:
    calendar = _weekday_calendar()
    friday_night = datetime(2026, 9, 4, 21, 5, tzinfo=SHANGHAI)
    trading_date = calendar.trading_date_for(friday_night)
    assert trading_date.isoformat() == "2026-09-07"


def test_day_session_keeps_same_calendar_date() -> None:
    calendar = _weekday_calendar()
    tuesday_day = datetime(2026, 9, 8, 10, 0, tzinfo=SHANGHAI)
    assert calendar.trading_date_for(tuesday_day).isoformat() == "2026-09-08"
