from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.domain.enums import AnalysisHorizon, DataStatus, FactorName
from dragonboat_ai.futures_agent.domain.market_data import (
    ContinuousBar,
    CurvePoint,
    CurveSnapshot,
    DailyBar,
    MarketContext,
)
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FactorAssessment
from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
from dragonboat_ai.futures_agent.features.registry import (
    DEFERRED_FEATURES,
    available_feature_names,
    available_features,
    registry_fingerprint,
    require_compatible_series,
    SeriesTypeMismatchError,
)
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig
from dragonboat_ai.futures_agent.scoring.direction_engine import DirectionEngine
from dragonboat_ai.futures_agent.scoring.factor_engine import DeterministicFactorEngine

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
STALE = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)


def test_registry_covers_baseline_metrics() -> None:
    names = available_feature_names()
    assert len(names) == 29
    assert "adx_14" not in names
    assert "basis" not in names
    assert {item.name for item in DEFERRED_FEATURES} == {"adx_14", "basis"}
    for spec in available_features():
        assert spec.window >= 1
        assert spec.min_samples >= 1
        assert spec.formula
        assert spec.series_type


def test_wrong_series_type_is_rejected() -> None:
    with pytest.raises(SeriesTypeMismatchError, match="research_index"):
        require_compatible_series("return_20d", "selected_contract")
    with pytest.raises(SeriesTypeMismatchError, match="not in the current available"):
        require_compatible_series("adx_14", "research_index")
    require_compatible_series("extension_atr", "selected_contract")


def _bar(trading_date: date, settlement: str, *, available_at: datetime = NOW) -> DailyBar:
    price = Decimal(settlement)
    return DailyBar(
        contract_id=1,
        contract="RB2701",
        trading_date=trading_date,
        open=price,
        high=price,
        low=price,
        close=price,
        settlement=price,
        previous_settlement=None,
        volume=100,
        turnover=None,
        open_interest=200,
        upper_limit=None,
        lower_limit=None,
        revision_no=1,
        available_at=available_at,
        source="test",
        payload_hash=f"{trading_date}",
    )


def _continuous(trading_date: date, settlement: str, *, available_at: datetime = STALE) -> ContinuousBar:
    price = Decimal(settlement)
    return ContinuousBar(
        instrument_id=1,
        symbol="RB",
        trading_date=trading_date,
        source_contract_id=9,
        source_contract="RB0000",
        raw_settlement=price,
        research_index=price,
        adjusted_settlement=price,
        adjustment_value=Decimal("0"),
        roll_flag=False,
        available_at=available_at,
        input_hash=f"c-{trading_date}",
    )


def _context(*, contract_bars, continuous_bars, curves=(), current=None) -> MarketContext:
    return MarketContext(
        request=AnalysisRequest(symbol="RB", as_of=NOW),
        instrument_id=1,
        contract_id=1,
        exchange="SHFE",
        symbol="RB",
        selected_contract="RB2701",
        contract_bars=tuple(contract_bars),
        continuous_bars=tuple(continuous_bars),
        current_curve=current,
        historical_curves=tuple(curves),
        days_to_expiry=120,
        recent_roll_date=None,
        contract_selection_reason="test",
        input_data_hash="registry",
    )


def test_stale_continuous_does_not_hide_behind_fresh_contract() -> None:
    start = date(2026, 8, 1)
    contract_bars = [_bar(start + timedelta(days=index), "3500", available_at=NOW) for index in range(30)]
    continuous_bars = [_continuous(start + timedelta(days=index), "3500", available_at=STALE) for index in range(30)]
    metrics = ReferenceFeatureEngine().compute(_context(contract_bars=contract_bars, continuous_bars=continuous_bars))
    assert metrics["return_20d"].available_at == STALE
    assert metrics["contract_return_5d"].available_at == NOW
    assert metrics["return_20d"].valid_n == 21
    assert metrics["return_20d"].valid_n != len(continuous_bars)


def _point(code: str, dte: int, settlement: str) -> CurvePoint:
    return CurvePoint(
        contract_id=hash(code) % 10_000,
        contract=code,
        expiry_date=date(2027, 1, 15),
        days_to_expiry=dte,
        settlement=Decimal(settlement),
        volume=100_000,
        open_interest=200_000,
    )


def _curve(trading_date: date, points: tuple[CurvePoint, ...]) -> CurveSnapshot:
    return CurveSnapshot(
        snapshot_id=f"c-{trading_date}",
        instrument_id=1,
        exchange="SHFE",
        symbol="RB",
        trading_date=trading_date,
        observed_at=NOW,
        available_at=NOW,
        points=points,
        source="test",
        input_hash=f"h-{trading_date}",
    )


def test_curve_change_not_caused_by_pair_switch() -> None:
    old_pair = (
        _point("RB2610", 20, "3600"),
        _point("RB2701", 80, "3500"),
        _point("RB2705", 140, "3480"),
    )
    new_pair = (
        _point("RB2701", 20, "4000"),
        _point("RB2705", 80, "3000"),
        _point("RB2709", 140, "2900"),
    )
    history = [_curve(date(2026, 8, 1) + timedelta(days=index), old_pair) for index in range(25)]
    current = _curve(date(2026, 9, 4), new_pair)
    metrics = ReferenceFeatureEngine().compute(
        _context(contract_bars=[], continuous_bars=[], curves=history, current=current)
    )
    assert metrics["curve_slope"].value is not None
    assert metrics["curve_slope_change_20d"].value is None
    assert metrics["curve_slope_change_20d"].normalized_score is None


def test_missing_curve_change_has_no_strengthening() -> None:
    points = (
        _point("RB2701", 30, "3500"),
        _point("RB2705", 90, "3480"),
    )
    current = _curve(date(2026, 9, 4), points)
    metrics = ReferenceFeatureEngine().compute(
        _context(contract_bars=[], continuous_bars=[], curves=(), current=current)
    )
    assert metrics["curve_slope"].value is not None
    assert metrics["curve_slope_change_20d"].value is None
    assert metrics["curve_slope_change_20d"].normalized_score is None


def _factor(name: FactorName, score: float | None, status: DataStatus = DataStatus.OK) -> FactorAssessment:
    return FactorAssessment(
        factor=name,
        status=status,
        score=score,
        coverage=100 if score is not None else 0,
        confidence=90 if score is not None else 0,
    )


def test_direction_coverage_boundary_70() -> None:
    base = ScoringConfig.default()
    fail_cfg = replace(
        base,
        direction_weights={
            "swing": {"trend": 0.69, "momentum": 0.11, "positioning": 0.10, "term_structure": 0.10},
            "position": {"trend": 0.69, "momentum": 0.11, "positioning": 0.10, "term_structure": 0.10},
        },
    )
    pass_cfg = replace(
        base,
        direction_weights={
            "swing": {"trend": 0.70, "momentum": 0.10, "positioning": 0.10, "term_structure": 0.10},
            "position": {"trend": 0.70, "momentum": 0.10, "positioning": 0.10, "term_structure": 0.10},
        },
    )
    only_trend = [
        _factor(FactorName.TREND, 80),
        _factor(FactorName.MOMENTUM, None, DataStatus.MISSING),
        _factor(FactorName.POSITIONING, None, DataStatus.MISSING),
        _factor(FactorName.TERM_STRUCTURE, None, DataStatus.MISSING),
    ]
    failed = DirectionEngine(fail_cfg).assess(AnalysisHorizon.SWING, only_trend)
    passed = DirectionEngine(pass_cfg).assess(AnalysisHorizon.SWING, only_trend)
    assert failed.score is None
    assert passed.score == 80


def test_missing_not_filled_with_zero() -> None:
    factors = [
        _factor(FactorName.TREND, 80),
        _factor(FactorName.MOMENTUM, 40),
        _factor(FactorName.POSITIONING, 20),
        _factor(FactorName.TERM_STRUCTURE, None, DataStatus.MISSING),
    ]
    result = DirectionEngine().assess(AnalysisHorizon.SWING, factors)
    assert result.score != 0.40 * 80 + 0.25 * 40 + 0.15 * 20 + 0.20 * 0
    assert result.score == (0.40 * 80 + 0.25 * 40 + 0.15 * 20) / 0.80


def test_trend_momentum_share_return_20d_lineage() -> None:
    start = date(2026, 1, 1)
    continuous = [_continuous(start + timedelta(days=index), str(3000 + index)) for index in range(130)]
    contract = [_bar(start + timedelta(days=index), str(3000 + index)) for index in range(130)]
    metrics = ReferenceFeatureEngine().compute(_context(contract_bars=contract, continuous_bars=continuous))
    factors, _ = DeterministicFactorEngine().score(
        _context(contract_bars=contract, continuous_bars=continuous),
        metrics,
    )
    by_name = {item.factor: item for item in factors}
    trend_ids = next(item.lineage_id for item in by_name[FactorName.TREND].contributions if item.feature_name == "return_20d")
    mom_ids = next(item.lineage_id for item in by_name[FactorName.MOMENTUM].contributions if item.feature_name == "return_20d")
    assert trend_ids == mom_ids == "return_20d"
    trend_metric = next(item.metric_ids[0] for item in by_name[FactorName.TREND].contributions if item.feature_name == "return_20d")
    mom_metric = next(item.metric_ids[0] for item in by_name[FactorName.MOMENTUM].contributions if item.feature_name == "return_20d")
    assert trend_metric == mom_metric


def test_feature_snapshot_identity_changes_with_config() -> None:
    base = ScoringConfig.default()
    changed = replace(base, minimum_available_weight=0.71)
    assert base.fingerprint() != changed.fingerprint()
    assert registry_fingerprint() == registry_fingerprint()
    assert ReferenceFeatureEngine.FEATURE_SET_VERSION == "futures_features_v1_3"
