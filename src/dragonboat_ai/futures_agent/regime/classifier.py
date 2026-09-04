from __future__ import annotations

from dragonboat_ai.futures_agent.domain.enums import DataStatus, FactorName
from dragonboat_ai.futures_agent.domain.models import FactorAssessment, MarketRegime, MetricObservation
from dragonboat_ai.futures_agent.features.normalization import clip

from dragonboat_ai.futures_agent.scoring.config import ScoringConfig


class RuleBasedRegimeClassifier:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig.default()

    def classify(
        self,
        factors: list[FactorAssessment],
        metrics: dict[str, MetricObservation],
    ) -> MarketRegime:
        by_factor = {factor.factor: factor for factor in factors}
        trend = self._score(by_factor.get(FactorName.TREND))
        momentum = self._score(by_factor.get(FactorName.MOMENTUM))
        positioning = self._score(by_factor.get(FactorName.POSITIONING))
        curve = self._score(by_factor.get(FactorName.TERM_STRUCTURE))

        primary = self._primary(trend)
        secondary: list[str] = []
        hypotheses: list[str] = []

        if trend is not None and momentum is not None:
            if trend >= 20 and momentum >= 40:
                secondary.append("trend_acceleration")
            elif trend <= -20 and momentum <= -40:
                secondary.append("trend_acceleration")
            elif trend >= 20 and momentum <= -20:
                secondary.append("pullback_in_bull_trend")
            elif trend <= -20 and momentum >= 20:
                secondary.append("rebound_in_bear_trend")
            elif abs(momentum) < 15 and abs(trend) >= 30:
                secondary.append("trend_deceleration")

        curve_change = self._metric_score(metrics, "curve_slope_change_20d")
        if curve is not None:
            if curve >= 30 and (curve_change is None or curve_change >= 0):
                secondary.append("backwardation_strengthening")
            elif curve >= 30:
                secondary.append("backwardation_weakening")
            elif curve <= -30 and (curve_change is None or curve_change <= 0):
                secondary.append("contango_strengthening")
            elif curve <= -30:
                secondary.append("contango_weakening")

        oi_change = self._metric_value(metrics, "oi_change_5d")
        price_return = self._metric_value(metrics, "contract_return_5d")
        if oi_change is not None and positioning is not None:
            if oi_change > 0 and abs(positioning) >= 20:
                secondary.append("position_building")
            elif oi_change < 0 and abs(positioning) >= 15:
                secondary.append("position_liquidation")
        if price_return is not None and oi_change is not None:
            if price_return > 0 and oi_change < 0:
                hypotheses.append("possible_short_covering_rally")
            elif price_return < 0 and oi_change < 0:
                hypotheses.append("possible_long_liquidation")

        volatility = self._volatility_regime(self._metric_value(metrics, "volatility_percentile"))
        liquidity = self._liquidity_regime(self._metric_value(metrics, "liquidity_quality_score"))
        valid_confidences = [
            factor.confidence
            for factor in factors
            if factor.status in {DataStatus.OK, DataStatus.PARTIAL} and factor.score is not None
        ]
        confidence = sum(valid_confidences) / len(valid_confidences) if valid_confidences else 0.0
        return MarketRegime(
            primary=primary,
            secondary=list(dict.fromkeys(secondary)),
            volatility_regime=volatility,
            liquidity_regime=liquidity,
            regime_confidence=clip(confidence, 0.0, 100.0),
            hypothesis_labels=hypotheses,
        )

    @staticmethod
    def _score(factor: FactorAssessment | None) -> float | None:
        return factor.score if factor and factor.status in {DataStatus.OK, DataStatus.PARTIAL} else None

    @staticmethod
    def _metric_value(metrics: dict[str, MetricObservation], name: str) -> float | None:
        metric = metrics.get(name)
        return metric.value if metric else None

    @staticmethod
    def _metric_score(metrics: dict[str, MetricObservation], name: str) -> float | None:
        metric = metrics.get(name)
        return metric.normalized_score if metric else None

    @staticmethod
    def _primary(trend: float | None) -> str:
        if trend is None:
            return "insufficient_data"
        if trend >= 60:
            return "strong_bull_trend"
        if trend >= 20:
            return "weak_bull_trend"
        if trend <= -60:
            return "strong_bear_trend"
        if trend <= -20:
            return "weak_bear_trend"
        return "range"

    def _volatility_regime(self, percentile: float | None) -> str:
        if percentile is None:
            return "unknown"
        thresholds = self.config.volatility_thresholds
        if percentile >= thresholds["extreme_percentile"]:
            return "extreme"
        if percentile >= thresholds["high_percentile"]:
            return "high"
        if percentile < thresholds["low_percentile"]:
            return "low"
        return "normal"

    @staticmethod
    def _liquidity_regime(quality: float | None) -> str:
        if quality is None:
            return "unknown"
        if quality >= 70:
            return "high"
        if quality >= 40:
            return "normal"
        if quality >= 20:
            return "low"
        return "illiquid"
