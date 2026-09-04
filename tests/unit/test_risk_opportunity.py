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
from dragonboat_ai.futures_agent.scoring.opportunity_engine import OpportunityEngine
from dragonboat_ai.futures_agent.scoring.risk_engine import RiskEngine

NOW = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)


def metric(name: str, value: float) -> MetricObservation:
    return MetricObservation(
        metric_id=f"metric-{name}",
        name=name,
        value=value,
        unit="score",
        normalized_score=max(-100.0, min(100.0, value)),
        observation_time=NOW,
        available_at=NOW,
        source="test",
    )


def context(days_to_expiry: int) -> MarketContext:
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


def data_quality(score: float = 90) -> DataQualityAssessment:
    return DataQualityAssessment(
        status=DataStatus.OK,
        overall_score=score,
        required_data_coverage=score,
    )


def test_expiry_hard_gate_forces_extreme_risk() -> None:
    result = RiskEngine().assess(
        context=context(3),
        metrics={
            "volatility_percentile": metric("volatility_percentile", 50),
            "liquidity_quality_score": metric("liquidity_quality_score", 80),
            "roll_risk_score": metric("roll_risk_score", 100),
        },
        data_quality=data_quality(),
    )
    assert result.hard_gate_triggered is True
    assert result.level is RiskLevel.EXTREME
    assert result.score == 100


def test_bullish_but_overextended_waits_for_pullback() -> None:
    direction = DirectionAssessment(
        horizon=AnalysisHorizon.SWING,
        score=75,
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
        context=context(120),
        metrics={
            "volatility_percentile": metric("volatility_percentile", 55),
            "liquidity_quality_score": metric("liquidity_quality_score", 85),
            "roll_risk_score": metric("roll_risk_score", 0),
        },
        data_quality=data_quality(),
    )
    result = OpportunityEngine().assess(
        direction=direction,
        regime=regime,
        risk=risk,
        confidence=confidence,
        metrics={
            "extension_atr": metric("extension_atr", 3.2),
            "rsi_14": metric("rsi_14", 82),
            "liquidity_quality_score": metric("liquidity_quality_score", 85),
        },
    )
    assert result.action.value == "wait_for_pullback"
    assert result.entry_quality < 30
