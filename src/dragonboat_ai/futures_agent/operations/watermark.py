from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


class WatermarkStatus(str, Enum):
    READY = "ready"
    TOO_EARLY = "too_early"
    MISSING = "missing_settlement"
    STALE = "stale"
    LOOKAHEAD_BLOCKED = "lookahead_blocked"


@dataclass(frozen=True, slots=True)
class ExchangeWatermark:
    exchange: str
    session_close: time
    timezone_name: str = "Asia/Shanghai"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


# Session close is the watermark, not a global 16:30 clock.
EXCHANGE_WATERMARKS = {
    "SHFE": ExchangeWatermark("SHFE", time(15, 0)),
    "DCE": ExchangeWatermark("DCE", time(15, 0)),
    "CZCE": ExchangeWatermark("CZCE", time(15, 0)),
    "INE": ExchangeWatermark("INE", time(15, 0)),
    "CFFEX": ExchangeWatermark("CFFEX", time(15, 15)),
    "GFEX": ExchangeWatermark("GFEX", time(15, 0)),
}


@dataclass(frozen=True, slots=True)
class WatermarkDecision:
    status: WatermarkStatus
    run: bool
    degrade: bool
    reason: str


def evaluate_watermark(
    *,
    exchange: str,
    session_date: date,
    now: datetime,
    settlement_available_at: datetime | None,
) -> WatermarkDecision:
    """Run only after the exchange session is closed and settlement is already visible."""
    watermark = EXCHANGE_WATERMARKS.get(exchange.upper())
    if watermark is None:
        raise ValueError(f"No watermark policy for exchange {exchange}")
    now = now.astimezone(watermark.tz)
    session_close = datetime.combine(session_date, watermark.session_close, tzinfo=watermark.tz)
    if now < session_close:
        return WatermarkDecision(
            status=WatermarkStatus.TOO_EARLY,
            run=False,
            degrade=False,
            reason="session still open; refusing to read final settlement",
        )
    if settlement_available_at is None:
        return WatermarkDecision(
            status=WatermarkStatus.MISSING,
            run=False,
            degrade=True,
            reason="settlement not published; gap must be recorded",
        )
    available = settlement_available_at.astimezone(watermark.tz)
    if available > now:
        return WatermarkDecision(
            status=WatermarkStatus.LOOKAHEAD_BLOCKED,
            run=False,
            degrade=True,
            reason="settlement timestamp is in the future of now",
        )
    if available.date() < session_date:
        return WatermarkDecision(
            status=WatermarkStatus.STALE,
            run=False,
            degrade=True,
            reason="visible settlement belongs to an earlier session",
        )
    return WatermarkDecision(
        status=WatermarkStatus.READY,
        run=True,
        degrade=False,
        reason="session closed and settlement visible",
    )
