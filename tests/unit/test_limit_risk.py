from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dragonboat_ai.futures_agent.domain.enums import DataStatus
from dragonboat_ai.futures_agent.domain.market_data import DailyBar, MarketContext
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def _bar(*, settlement: str, upper: str | None, lower: str | None) -> DailyBar:
    price = Decimal(settlement)
    return DailyBar(
        contract_id=1,
        contract="RB2701",
        trading_date=date(2026, 9, 4),
        open=price,
        high=price,
        low=price,
        close=price,
        settlement=price,
        previous_settlement=None,
        volume=100,
        turnover=None,
        open_interest=200,
        upper_limit=Decimal(upper) if upper is not None else None,
        lower_limit=Decimal(lower) if lower is not None else None,
        revision_no=1,
        available_at=NOW,
        source="test",
        payload_hash="limit",
    )


def _context(bar: DailyBar) -> MarketContext:
    return MarketContext(
        request=AnalysisRequest(symbol="RB", contract="RB2701", as_of=NOW),
        instrument_id=1,
        contract_id=1,
        exchange="SHFE",
        symbol="RB",
        selected_contract="RB2701",
        contract_bars=(bar,),
        continuous_bars=(),
        current_curve=None,
        historical_curves=(),
        days_to_expiry=120,
        recent_roll_date=None,
        contract_selection_reason="test",
        input_data_hash="limit",
    )


def test_limit_equality_is_max_risk() -> None:
    metrics = ReferenceFeatureEngine().compute(_context(_bar(settlement="3500", upper="3500", lower="3200")))
    limit = metrics["price_limit_proximity_risk"]
    assert limit.value == 100.0
    assert limit.status is DataStatus.OK


def test_limit_breach_is_invalid() -> None:
    metrics = ReferenceFeatureEngine().compute(_context(_bar(settlement="3510", upper="3500", lower="3200")))
    limit = metrics["price_limit_proximity_risk"]
    assert limit.status is DataStatus.INVALID
    assert limit.value is None or limit.value == 100.0
