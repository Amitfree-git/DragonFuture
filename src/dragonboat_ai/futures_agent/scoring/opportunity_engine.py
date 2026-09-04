from __future__ import annotations

from dragonboat_ai.futures_agent.domain.enums import OpportunityAction, TradeSide
from dragonboat_ai.futures_agent.domain.models import (
    ConfidenceAssessment,
    DirectionAssessment,
    MarketRegime,
    MetricObservation,
    OpportunityAssessment,
    RiskAssessment,
)
from dragonboat_ai.futures_agent.features.normalization import clip

from .config import ScoringConfig


class OpportunityEngine:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig.default()

    def assess(
        self,
        *,
        direction: DirectionAssessment,
        regime: MarketRegime,
        risk: RiskAssessment,
        confidence: ConfidenceAssessment,
        metrics: dict[str, MetricObservation],
    ) -> OpportunityAssessment:
        hard_reasons: list[str] = []
        if direction.score is None:
            hard_reasons.append("insufficient_direction_data")
        if risk.hard_gate_triggered:
            hard_reasons.extend(item.risk_code for item in risk.items if item.hard_gate)
        if risk.score >= self.config.hard_gates["risk_score"]:
            hard_reasons.append("risk_score_above_limit")
        if confidence.score < self.config.hard_gates["confidence_score"]:
            hard_reasons.append("confidence_below_limit")
        if direction.score is not None and abs(direction.score) < self.config.hard_gates["minimum_direction_abs_score"]:
            hard_reasons.append("direction_too_weak")

        side = (
            TradeSide.LONG
            if direction.score is not None and direction.score > 0
            else TradeSide.SHORT
            if direction.score is not None and direction.score < 0
            else TradeSide.NONE
        )
        entry_quality = self._entry_quality(side, metrics)
        regime_fit = self._regime_fit(side, regime)
        liquidity = self._metric_value(metrics, "liquidity_quality_score", default=50.0)

        if direction.score is None:
            score = 0.0
        else:
            weights = self.config.opportunity_weights
            score = (
                weights["direction_strength"] * abs(direction.score)
                + weights["entry_quality"] * entry_quality
                + weights["regime_fit"] * regime_fit
                + weights["liquidity_quality"] * liquidity
                - weights["risk_penalty"] * risk.score
            )
            score = clip(score, 0.0, 100.0)

        if "insufficient_direction_data" in hard_reasons:
            action = OpportunityAction.INSUFFICIENT_DATA
        elif hard_reasons:
            action = OpportunityAction.NO_TRADE
        else:
            action = self._action(side, score, regime, metrics)

        return OpportunityAssessment(
            side=side,
            action=action,
            score=score,
            entry_quality=entry_quality,
            regime_fit=regime_fit,
            liquidity_quality=liquidity,
            hard_gate_reasons=sorted(set(hard_reasons)),
        )

    def _entry_quality(self, side: TradeSide, metrics: dict[str, MetricObservation]) -> float:
        extension = self._metric_value(metrics, "extension_atr", default=0.0)
        rsi = self._metric_value(metrics, "rsi_14", default=50.0)
        quality = 75.0
        if side is TradeSide.LONG:
            quality -= max(extension - 1.0, 0.0) * 22.0
            quality -= max(rsi - 65.0, 0.0) * 1.4
            quality += max(min(-extension, 1.0), 0.0) * 10.0
        elif side is TradeSide.SHORT:
            quality -= max(-extension - 1.0, 0.0) * 22.0
            quality -= max(35.0 - rsi, 0.0) * 1.4
            quality += max(min(extension, 1.0), 0.0) * 10.0
        else:
            quality = 40.0
        return clip(quality, 0.0, 100.0)

    @staticmethod
    def _regime_fit(side: TradeSide, regime: MarketRegime) -> float:
        primary = regime.primary
        if side is TradeSide.LONG:
            if primary == "strong_bull_trend":
                return 90.0
            if primary == "weak_bull_trend":
                return 75.0
            if primary == "range":
                return 45.0
            return 15.0
        if side is TradeSide.SHORT:
            if primary == "strong_bear_trend":
                return 90.0
            if primary == "weak_bear_trend":
                return 75.0
            if primary == "range":
                return 45.0
            return 15.0
        return 30.0

    @staticmethod
    def _action(
        side: TradeSide,
        score: float,
        regime: MarketRegime,
        metrics: dict[str, MetricObservation],
    ) -> OpportunityAction:
        extension = OpportunityEngine._metric_value(metrics, "extension_atr", default=0.0)
        rsi = OpportunityEngine._metric_value(metrics, "rsi_14", default=50.0)
        if side is TradeSide.LONG and (extension >= 2.0 or rsi >= 75.0):
            return OpportunityAction.WAIT_FOR_PULLBACK
        if side is TradeSide.SHORT and (extension <= -2.0 or rsi <= 25.0):
            return OpportunityAction.WAIT_FOR_REBOUND
        if regime.primary == "range" and score < 50.0:
            return OpportunityAction.WAIT_FOR_BREAKOUT
        if score >= 45.0 and side is TradeSide.LONG:
            return OpportunityAction.LONG_CANDIDATE
        if score >= 45.0 and side is TradeSide.SHORT:
            return OpportunityAction.SHORT_CANDIDATE
        return OpportunityAction.NO_TRADE

    @staticmethod
    def _metric_value(
        metrics: dict[str, MetricObservation],
        name: str,
        *,
        default: float,
    ) -> float:
        metric = metrics.get(name)
        return float(metric.value) if metric is not None and metric.value is not None else default
