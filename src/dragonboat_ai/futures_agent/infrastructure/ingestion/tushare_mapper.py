from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.domain.bar_contract import validate_ohlc_settlement
from dragonboat_ai.futures_agent.domain.data_mode import DataMode
from dragonboat_ai.futures_agent.domain.market_data import DailyBar
from dragonboat_ai.futures_agent.infrastructure.ingestion.exchanges import parse_ts_code
from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")
TUSHARE_SOURCE = "tushare"
_WAN_YUAN = Decimal("10000")


@dataclass(frozen=True, slots=True)
class ContractMeta:
    ts_code: str
    exchange: str
    product: str
    contract_code: str
    name: str | None
    listed_date: date | None
    last_trade_date: date | None
    expiry_date: date
    delivery_month: str | None


def parse_trade_date(value: str) -> date:
    digits = value.replace("-", "").strip()
    if len(digits) != 8 or not digits.isdigit():
        raise ValueError(f"Expected YYYYMMDD trade date, got {value!r}")
    return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))


def settlement_available_at(trading_date: date) -> datetime:
    """Futures daily bars include the prior night session and finish at 15:00."""
    return datetime.combine(trading_date, time(16, 0), tzinfo=SHANGHAI)


def map_contract_basic(row: Mapping[str, Any]) -> ContractMeta | None:
    parsed = parse_ts_code(str(row["ts_code"]))
    delist = row.get("delist_date")
    if not delist:
        return None
    expiry_date = parse_trade_date(str(delist))
    list_date = row.get("list_date")
    exchange = str(row.get("exchange") or parsed.exchange).strip().upper()
    product = str(row.get("fut_code") or "").strip().upper()
    if not product:
        raise ValueError(f"Contract {parsed.ts_code} is missing fut_code")
    contract_code = str(row.get("symbol") or parsed.contract_code).strip().upper()
    delivery_month = row.get("d_month")
    return ContractMeta(
        ts_code=parsed.ts_code,
        exchange=exchange,
        product=product,
        contract_code=contract_code,
        name=(str(row["name"]) if row.get("name") else None),
        listed_date=parse_trade_date(str(list_date)) if list_date else None,
        last_trade_date=expiry_date,
        expiry_date=expiry_date,
        delivery_month=str(delivery_month) if delivery_month else None,
    )


def map_fut_daily_bar(row: Mapping[str, Any], *, contract_id: int) -> DailyBar | None:
    settle = row.get("settle")
    volume = row.get("vol")
    open_interest = row.get("oi")
    open_price = row.get("open")
    high_price = row.get("high")
    low_price = row.get("low")
    close_price = row.get("close")
    if any(
        value is None
        for value in (settle, volume, open_interest, open_price, high_price, low_price, close_price)
    ):
        return None

    parsed = parse_ts_code(str(row["ts_code"]))
    trading_date = parse_trade_date(str(row["trade_date"]))
    previous_settlement = row.get("pre_settle")
    amount = row.get("amount")
    open_value = _as_decimal(open_price)
    high_value = _as_decimal(high_price)
    low_value = _as_decimal(low_price)
    close_value = _as_decimal(close_price)
    settlement = _as_decimal(settle)
    validate_ohlc_settlement(
        open_=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        settlement=settlement,
    )
    published = settlement_available_at(trading_date)
    return DailyBar(
        contract_id=contract_id,
        contract=parsed.contract_code,
        trading_date=trading_date,
        open=open_value,
        high=high_value,
        low=low_value,
        close=close_value,
        settlement=settlement,
        previous_settlement=_as_decimal(previous_settlement) if previous_settlement is not None else None,
        volume=int(volume),
        turnover=_as_decimal(amount) * _WAN_YUAN if amount is not None else None,
        open_interest=int(open_interest),
        upper_limit=None,
        lower_limit=None,
        revision_no=1,
        available_at=published,
        source=TUSHARE_SOURCE,
        payload_hash=stable_payload_hash(dict(row)),
        published_at=published,
        received_at=published,
        data_mode=DataMode.FINAL_ONLY.value,
    )


def _as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))
