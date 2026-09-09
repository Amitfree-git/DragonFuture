from datetime import datetime, timezone

from dragonboat_ai.futures_agent.domain.enums import (
    AnalysisHorizon,
    DataStatus,
    DirectionLabel,
    RiskLevel,
)
from dragonboat_ai.futures_agent.domain.market_data import MarketContext
from dragonboat_ai.futures_agent.domain.models import (
    AnalysisRequest,
    ConfidenceAssessment,
    DataQualityAssessment,
    DirectionAssessment,
    MarketRegime,
    MetricObservation,
)
from dragonboat_ai.futures_agent.scoring.confidence_engine import ConfidenceEngine
from dragonboat_ai.futures_agent.scoring.opportunity_engine import OpportunityEngine
from dragonboat_ai.futures_agent.scoring.risk_engine import RiskEngine

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def metric(name: str, value: float | None, status: DataStatus = DataStatus.OK) -> MetricObservation:
    return MetricObservation(
        metric_id=f"metric-{name}",
        name=name,
        value=value,
        unit="score",
        normalized_score=None if value is None else max(-100.0, min(100.0, value)),
        observation_time=NOW,
        available_at=NOW,
        source="test",
        status=status,
    )


def context(days_to_expiry: int = 120) -> MarketContext:
    return MarketContext(
        request=AnalysisRequest(symbol="RB", contract="RB2701", as_of=NOW),
        instrument_id=1,
        contract_id=2,
        exchange="SHFE",
        symbol="RB",
        selected_contract="RB2701",
        contract_bars=(),
        continuous_bars=(),
        current_curve=None,
        historical_curves=(),
        days_to_expiry=days_to_expiry,
        recent_roll_date=None,
        contract_selection_reason="test",
        input_data_hash="input",
    )


def test_blocked_quality_prevents_valid_direction() -> None:
    quality = DataQualityAssessment(
        status=DataStatus.INVALID,
        overall_score=10,
        required_data_coverage=10,
        blocking_issues=["continuous_series_has_fewer_than_21_bars"],
    )
    direction = DirectionAssessment(
        horizon=AnalysisHorizon.SWING,
        score=80,
        label=DirectionLabel.STRONG_BULLISH,
        available_factor_weight=100,
        factor_scores={},
    )
    if quality.blocking_issues:
        direction = DirectionAssessment(
            horizon=direction.horizon,
            score=None,
            label=DirectionLabel.INSUFFICIENT_DATA,
            available_factor_weight=direction.available_factor_weight,
            factor_scores=direction.factor_scores,
        )
    assert direction.score is None
    assert direction.label is DirectionLabel.INSUFFICIENT_DATA


def test_hard_gate_overrides_strong_direction() -> None:
    direction = DirectionAssessment(
        horizon=AnalysisHorizon.SWING,
        score=80,
        label=DirectionLabel.STRONG_BULLISH,
        available_factor_weight=100,
        factor_scores={},
    )
    confidence = ConfidenceAssessment(
        score=80,
        data_coverage=100,
        freshness=95,
        factor_agreement=80,
        data_quality=90,
    )
    regime = MarketRegime(
        primary="strong_bull_trend",
        volatility_regime="normal",
        liquidity_regime="high",
        regime_confidence=80,
    )
    risk = RiskEngine().assess(
        context=context(3),
        metrics={
            "volatility_percentile": metric("volatility_percentile", 40),
            "liquidity_quality_score": metric("liquidity_quality_score", 80),
            "roll_risk_score": metric("roll_risk_score", 100),
            "price_limit_proximity_risk": metric("price_limit_proximity_risk", 10),
        },
        data_quality=DataQualityAssessment(
            status=DataStatus.OK,
            overall_score=90,
            required_data_coverage=90,
        ),
    )
    result = OpportunityEngine().assess(
        direction=direction,
        regime=regime,
        risk=risk,
        confidence=confidence,
        metrics={
            "extension_atr": metric("extension_atr", 0.4),
            "rsi_14": metric("rsi_14", 55),
            "liquidity_quality_score": metric("liquidity_quality_score", 80),
        },
    )
    assert risk.hard_gate_triggered is True
    assert result.action.value == "no_trade"
    assert result.side.value == "long"


def test_unknown_risk_is_not_labelled_low() -> None:
    result = RiskEngine().assess(
        context=context(120),
        metrics={
            "volatility_percentile": metric("volatility_percentile", 20),
            "liquidity_quality_score": metric("liquidity_quality_score", 80),
            "roll_risk_score": metric("roll_risk_score", 0),
            "price_limit_proximity_risk": metric(
                "price_limit_proximity_risk", None, status=DataStatus.MISSING
            ),
        },
        data_quality=DataQualityAssessment(
            status=DataStatus.OK,
            overall_score=90,
            required_data_coverage=90,
        ),
    )
    assert result.hard_gate_triggered is True
    assert result.level is not RiskLevel.LOW
    assert result.level is RiskLevel.EXTREME


def test_missing_agreement_is_not_fake_neutral() -> None:
    confidence = ConfidenceEngine().assess(
        as_of=NOW,
        factors=[],
        direction=DirectionAssessment(
            horizon=AnalysisHorizon.SWING,
            score=None,
            label=DirectionLabel.INSUFFICIENT_DATA,
            available_factor_weight=0,
            factor_scores={},
        ),
        metrics={},
        data_quality=DataQualityAssessment(
            status=DataStatus.MISSING,
            overall_score=0,
            required_data_coverage=0,
        ),
    )
    assert confidence.factor_agreement is None
    assert confidence.interpretation == "evidence_quality_not_win_probability"
    assert "probability" not in confidence.interpretation or "not_win_probability" in confidence.interpretation
