from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from dragonboat_ai.futures_agent.domain.market_data import DailyBar, MarketContext
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
from dragonboat_ai.futures_agent.features.statistics import realized_volatility

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def test_volume_window_matches_name() -> None:
    start = date(2026, 6, 1)
    bars = []
    for index in range(61):
        volume = 1_000_000 if index < 40 else 100 + (index % 5)
        if index == 60:
            volume = 400
        trading_date = start + timedelta(days=index)
        price = Decimal("3500")
        bars.append(
            DailyBar(
                contract_id=1,
                contract="RB2701",
                trading_date=trading_date,
                open=price,
                high=price,
                low=price,
                close=price,
                settlement=price,
                previous_settlement=None,
                volume=volume,
                turnover=None,
                open_interest=200,
                upper_limit=None,
                lower_limit=None,
                revision_no=1,
                available_at=NOW,
                source="test",
                payload_hash=f"vol-{index}",
            )
        )
    context = MarketContext(
        request=AnalysisRequest(symbol="RB", contract="RB2701", as_of=NOW),
        instrument_id=1,
        contract_id=1,
        exchange="SHFE",
        symbol="RB",
        selected_contract="RB2701",
        contract_bars=tuple(bars),
        continuous_bars=(),
        current_curve=None,
        historical_curves=(),
        days_to_expiry=120,
        recent_roll_date=None,
        contract_selection_reason="test",
        input_data_hash="volume",
    )
    zscore = ReferenceFeatureEngine().compute(context)["volume_zscore_20d"].value
    assert zscore is not None
    assert zscore > 0


def test_nonpositive_log_domain_not_silently_dropped() -> None:
    values = [100.0] * 10 + [0.0] + [100.0] * 11
    assert realized_volatility(values, 20) is None


def test_flat_moving_averages_are_not_automatically_bearish() -> None:
    prices = [100.0] * 65
    score = ReferenceFeatureEngine._ma_structure(prices, 100.0, 100.0, 0.01)
    assert score is not None
    assert score >= 0.0
