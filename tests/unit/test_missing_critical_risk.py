from datetime import datetime, timezone

from dragonboat_ai.futures_agent.domain.enums import (
    AnalysisHorizon,
    DataStatus,
    DirectionLabel,
    OpportunityAction,
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
        quality_score=0.0 if status is not DataStatus.OK else 100.0,
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


def _strong_long_inputs(metrics: dict[str, MetricObservation]):
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
        context=context(),
        metrics=metrics,
        data_quality=DataQualityAssessment(
            status=DataStatus.OK,
            overall_score=90,
            required_data_coverage=90,
        ),
    )
    opportunity = OpportunityEngine().assess(
        direction=direction,
        regime=regime,
        risk=risk,
        confidence=confidence,
        metrics=metrics,
    )
    return risk, opportunity


def test_missing_critical_risk_blocks_candidate() -> None:
    metrics = {
        "volatility_percentile": metric("volatility_percentile", 40),
        "roll_risk_score": metric("roll_risk_score", 0),
        "liquidity_quality_score": metric("liquidity_quality_score", None, DataStatus.MISSING),
        "price_limit_proximity_risk": metric("price_limit_proximity_risk", None, DataStatus.MISSING),
        "extension_atr": metric("extension_atr", 0.4),
        "rsi_14": metric("rsi_14", 55),
    }
    risk, opportunity = _strong_long_inputs(metrics)
    assert risk.hard_gate_triggered is True
    assert {item.risk_code for item in risk.items} >= {
        "unknown_liquidity_risk",
        "unknown_price_limit_risk",
    }
    assert opportunity.action is OpportunityAction.NO_TRADE
    assert opportunity.liquidity_quality == 0.0
    assert "missing_liquidity_quality" in opportunity.hard_gate_reasons


def test_invalid_price_limit_blocks_candidate() -> None:
    metrics = {
        "volatility_percentile": metric("volatility_percentile", 40),
        "roll_risk_score": metric("roll_risk_score", 0),
        "liquidity_quality_score": metric("liquidity_quality_score", 80),
        "price_limit_proximity_risk": metric(
            "price_limit_proximity_risk", None, DataStatus.INVALID
        ),
        "extension_atr": metric("extension_atr", 0.4),
        "rsi_14": metric("rsi_14", 55),
    }
    risk, opportunity = _strong_long_inputs(metrics)
    assert risk.hard_gate_triggered is True
    assert any(item.risk_code == "unknown_price_limit_risk" for item in risk.items)
    assert opportunity.action is OpportunityAction.NO_TRADE
