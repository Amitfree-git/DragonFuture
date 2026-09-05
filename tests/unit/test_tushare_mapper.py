from datetime import date, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import (
    map_contract_basic,
    map_fut_daily_bar,
    parse_trade_date,
    settlement_available_at,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

RB2701_BASIC = {
    "ts_code": "RB2701.SHF",
    "symbol": "RB2701",
    "exchange": "SHFE",
    "name": "螺纹钢2701",
    "fut_code": "RB",
    "multiplier": None,
    "list_date": "20260116",
    "delist_date": "20270115",
    "d_month": "202701",
    "last_ddate": "20270119",
}

RB2701_DAILY = {
    "ts_code": "RB2701.SHF",
    "trade_date": "20260904",
    "pre_close": 3142,
    "pre_settle": 3137,
    "open": 3145,
    "high": 3180,
    "low": 3137,
    "close": 3166,
    "settle": 3160,
    "change1": 29,
    "change2": 23,
    "vol": 877156,
    "amount": 2771976.949,
    "oi": 1497791,
    "oi_chg": 31308,
}


def test_parse_trade_date() -> None:
    assert parse_trade_date("20260904") == date(2026, 9, 4)


def test_settlement_available_at_is_after_day_session_not_midnight() -> None:
    available_at = settlement_available_at(date(2026, 9, 4))
    assert available_at.tzinfo is not None
    assert available_at.date() == date(2026, 9, 4)
    assert available_at.timetz().replace(tzinfo=None) == time(16, 0)
    assert available_at.tzinfo == SHANGHAI


def test_night_session_keeps_exchange_trading_date() -> None:
    """Tushare trade_date already includes the previous night session."""
    bar = map_fut_daily_bar(RB2701_DAILY, contract_id=7)
    assert bar is not None
    assert bar.trading_date == date(2026, 9, 4)
    assert bar.available_at == settlement_available_at(date(2026, 9, 4))


def test_map_contract_basic_uses_delist_as_expiry_not_delivery_date() -> None:
    meta = map_contract_basic(RB2701_BASIC)
    assert meta is not None
    assert meta.exchange == "SHFE"
    assert meta.product == "RB"
    assert meta.contract_code == "RB2701"
    assert meta.ts_code == "RB2701.SHF"
    assert meta.name == "螺纹钢2701"
    assert meta.listed_date == date(2026, 1, 16)
    assert meta.last_trade_date == date(2027, 1, 15)
    assert meta.expiry_date == date(2027, 1, 15)
    assert meta.delivery_month == "202701"


def test_continuous_contract_without_delist_is_skipped() -> None:
    row = {
        "ts_code": "RB.SHF",
        "symbol": "RB",
        "exchange": "SHFE",
        "name": "螺纹钢",
        "fut_code": "RB",
        "list_date": None,
        "delist_date": None,
        "d_month": None,
    }
    assert map_contract_basic(row) is None


def test_map_fut_daily_keeps_close_and_settlement_distinct() -> None:
    bar = map_fut_daily_bar(RB2701_DAILY, contract_id=7)
    assert bar is not None
    assert bar.contract_id == 7
    assert bar.contract == "RB2701"
    assert bar.close == Decimal("3166")
    assert bar.settlement == Decimal("3160")
    assert bar.previous_settlement == Decimal("3137")
    assert bar.open == Decimal("3145")
    assert bar.high == Decimal("3180")
    assert bar.low == Decimal("3137")


def test_map_fut_daily_converts_amount_from_wan_yuan() -> None:
    bar = map_fut_daily_bar(RB2701_DAILY, contract_id=7)
    assert bar is not None
    assert bar.turnover == Decimal("27719769490")
    assert bar.volume == 877156
    assert bar.open_interest == 1497791


def test_map_fut_daily_leaves_missing_limits_as_none() -> None:
    bar = map_fut_daily_bar(RB2701_DAILY, contract_id=7)
    assert bar is not None
    assert bar.upper_limit is None
    assert bar.lower_limit is None
    assert bar.source == "tushare"


def test_missing_settlement_is_not_coerced_to_zero() -> None:
    row = dict(RB2701_DAILY)
    row["settle"] = None
    assert map_fut_daily_bar(row, contract_id=7) is None


def test_missing_volume_is_not_coerced_to_zero() -> None:
    row = dict(RB2701_DAILY)
    row["vol"] = None
    assert map_fut_daily_bar(row, contract_id=7) is None
