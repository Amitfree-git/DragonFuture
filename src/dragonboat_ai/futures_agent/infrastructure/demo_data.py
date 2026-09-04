from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.domain.market_data import (
    ContinuousBar,
    CurvePoint,
    CurveSnapshot,
    DailyBar,
)
from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyMarketDataRepository,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


def business_days_ending(end: date, count: int) -> list[date]:
    result: list[date] = []
    current = end
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current -= timedelta(days=1)
    return list(reversed(result))


def visible_time(trading_date: date, minute: int = 10) -> datetime:
    return datetime.combine(trading_date, time(16, minute), tzinfo=SHANGHAI)


def decimal_price(value: float) -> Decimal:
    return Decimal(f"{value:.4f}")


def seed_reference_market(
    repository: SqlAlchemyMarketDataRepository,
    *,
    as_of: datetime | None = None,
) -> dict[str, object]:
    as_of = as_of or datetime(2026, 9, 4, 17, 0, tzinfo=SHANGHAI)
    instrument_id = repository.get_or_create_instrument(
        exchange="SHFE",
        symbol="RB",
        name="Rebar synthetic fixture",
    )
    rb2610 = repository.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2610",
        expiry_date=date(2026, 10, 15),
        listed_date=date(2025, 10, 16),
    )
    rb2701 = repository.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2701",
        expiry_date=date(2027, 1, 15),
        listed_date=date(2026, 1, 16),
    )
    rb2705 = repository.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2705",
        expiry_date=date(2027, 5, 15),
        listed_date=date(2026, 5, 16),
    )

    dates = business_days_ending(as_of.date(), 220)
    previous_contract_settlement: Decimal | None = None
    for index, trading_date in enumerate(dates):
        adjusted = 3300.0 + 1.25 * index + 16.0 * math.sin(index / 9.0)
        selected_price = adjusted - 7.0 + 2.0 * math.sin(index / 5.0)
        settlement = decimal_price(selected_price)
        bar = DailyBar(
            contract_id=rb2701.contract_id,
            contract=rb2701.contract_code,
            trading_date=trading_date,
            open=decimal_price(selected_price - 3.0),
            high=decimal_price(selected_price + 15.0),
            low=decimal_price(selected_price - 15.0),
            close=decimal_price(selected_price + 1.5),
            settlement=settlement,
            previous_settlement=previous_contract_settlement,
            volume=120_000 + index * 220 + int(4_000 * (1.0 + math.sin(index / 7.0))),
            turnover=Decimal("1000000000"),
            open_interest=210_000 + index * 420,
            upper_limit=decimal_price(selected_price * 1.08),
            lower_limit=decimal_price(selected_price * 0.92),
            revision_no=1,
            available_at=visible_time(trading_date, 5),
            source="synthetic_fixture",
            payload_hash=hashlib.sha256(f"bar|{trading_date}|{selected_price}".encode()).hexdigest(),
        )
        repository.add_daily_bar(bar)
        previous_contract_settlement = settlement

        source = rb2610 if index < 130 else rb2701
        raw = adjusted - (80.0 if source.contract_code == "RB2610" else 0.0)
        repository.add_continuous_bar(
            ContinuousBar(
                instrument_id=instrument_id,
                symbol="RB",
                trading_date=trading_date,
                source_contract_id=source.contract_id,
                source_contract=source.contract_code,
                raw_settlement=decimal_price(raw),
                adjusted_settlement=decimal_price(adjusted),
                adjustment_value=Decimal("80") if source.contract_code == "RB2610" else Decimal("0"),
                roll_flag=index == 130,
                available_at=visible_time(trading_date, 6),
                input_hash=hashlib.sha256(f"continuous|{trading_date}|{adjusted}".encode()).hexdigest(),
            )
        )

    for index, trading_date in enumerate(dates[-100:]):
        base = 3520.0 + 0.9 * index + 8.0 * math.sin(index / 8.0)
        points = (
            CurvePoint(
                contract_id=rb2610.contract_id,
                contract=rb2610.contract_code,
                expiry_date=rb2610.expiry_date,
                days_to_expiry=(rb2610.expiry_date - trading_date).days,
                settlement=decimal_price(base + 32.0),
                volume=90_000,
                open_interest=145_000,
            ),
            CurvePoint(
                contract_id=rb2701.contract_id,
                contract=rb2701.contract_code,
                expiry_date=rb2701.expiry_date,
                days_to_expiry=(rb2701.expiry_date - trading_date).days,
                settlement=decimal_price(base),
                volume=175_000 + index * 300,
                open_interest=270_000 + index * 500,
            ),
            CurvePoint(
                contract_id=rb2705.contract_id,
                contract=rb2705.contract_code,
                expiry_date=rb2705.expiry_date,
                days_to_expiry=(rb2705.expiry_date - trading_date).days,
                settlement=decimal_price(base - 42.0),
                volume=65_000,
                open_interest=100_000,
            ),
        )
        snapshot_id = f"RB-{trading_date.isoformat()}-r1"
        repository.add_curve_snapshot(
            CurveSnapshot(
                snapshot_id=snapshot_id,
                instrument_id=instrument_id,
                exchange="SHFE",
                symbol="RB",
                trading_date=trading_date,
                observed_at=datetime.combine(trading_date, time(15, 0), tzinfo=SHANGHAI),
                available_at=visible_time(trading_date, 10),
                points=points,
                source="synthetic_fixture",
                input_hash=hashlib.sha256(f"curve|{trading_date}|{base}".encode()).hexdigest(),
            )
        )

    return {
        "as_of": as_of,
        "instrument_id": instrument_id,
        "rb2610": rb2610,
        "rb2701": rb2701,
        "rb2705": rb2705,
    }
