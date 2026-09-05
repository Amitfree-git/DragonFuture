from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.domain.data_mode import require_aware_utc


@dataclass(frozen=True, slots=True)
class SessionHours:
    night_open: time
    night_close: time
    day_open: time
    day_close: time


class ExchangeCalendar:
    """Versioned session map. The weekday helper is a test calendar, not an official holiday file."""

    def __init__(
        self,
        *,
        exchange: str,
        version: str,
        timezone_name: str,
        sessions: SessionHours,
        holidays: frozenset[date] = frozenset(),
        weekend_as_holiday: bool = True,
    ) -> None:
        self.exchange = exchange
        self.version = version
        self.tz = ZoneInfo(timezone_name)
        self.sessions = sessions
        self.holidays = holidays
        self.weekend_as_holiday = weekend_as_holiday

    @classmethod
    def weekday_sessions(
        cls,
        *,
        exchange: str,
        version: str,
        night_open: str,
        night_close: str,
        day_open: str,
        day_close: str,
        timezone_name: str = "Asia/Shanghai",
    ) -> ExchangeCalendar:
        parse = time.fromisoformat
        return cls(
            exchange=exchange,
            version=version,
            timezone_name=timezone_name,
            sessions=SessionHours(
                night_open=parse(night_open),
                night_close=parse(night_close),
                day_open=parse(day_open),
                day_close=parse(day_close),
            ),
        )

    def is_trading_day(self, value: date) -> bool:
        if self.weekend_as_holiday and value.weekday() >= 5:
            return False
        return value not in self.holidays

    def next_trading_day(self, value: date) -> date:
        current = value + timedelta(days=1)
        while not self.is_trading_day(current):
            current += timedelta(days=1)
        return current

    def trading_date_for(self, instant: datetime) -> date:
        local = require_aware_utc(instant).astimezone(self.tz)
        local_time = local.time()
        local_date = local.date()
        if self._in_night(local_time):
            wraps_midnight = self.sessions.night_close < self.sessions.night_open
            session_calendar_date = (
                local_date - timedelta(days=1)
                if wraps_midnight and local_time < self.sessions.night_close
                else local_date
            )
            return self.next_trading_day(session_calendar_date)
        if self.is_trading_day(local_date):
            return local_date
        return self.next_trading_day(local_date)

    def _in_night(self, local_time: time) -> bool:
        open_at = self.sessions.night_open
        close_at = self.sessions.night_close
        if open_at <= close_at:
            return open_at <= local_time < close_at
        return local_time >= open_at or local_time < close_at
