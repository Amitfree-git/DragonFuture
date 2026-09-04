from __future__ import annotations

from dragonboat_ai.futures_agent.domain.enums import AnalysisHorizon, DataStatus, DirectionLabel
from dragonboat_ai.futures_agent.domain.models import DirectionAssessment, FactorAssessment
from dragonboat_ai.futures_agent.features.normalization import clip

from .config import ScoringConfig


class DirectionEngine:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig.default()

    def assess(
        self,
        horizon: AnalysisHorizon,
        factors: list[FactorAssessment],
    ) -> DirectionAssessment:
        weights = self.config.direction_weights[horizon.value]
        factor_by_name = {factor.factor.value: factor for factor in factors}
        total_weight = sum(weights.values())
        available_weight = 0.0
        weighted_score = 0.0
        factor_scores: dict[str, float | None] = {}

        for name, weight in weights.items():
            factor = factor_by_name.get(name)
            score = factor.score if factor is not None else None
            factor_scores[name] = score
            if (
                factor is not None
                and factor.status in {DataStatus.OK, DataStatus.PARTIAL}
                and score is not None
            ):
                available_weight += weight
                weighted_score += weight * score

        coverage_ratio = available_weight / total_weight if total_weight else 0.0
        coverage = clip(coverage_ratio * 100.0, 0.0, 100.0)
        if coverage_ratio + 1e-12 < self.config.minimum_available_weight:
            return DirectionAssessment(
                horizon=horizon,
                score=None,
                label=DirectionLabel.INSUFFICIENT_DATA,
                available_factor_weight=coverage,
                factor_scores=factor_scores,
            )

        score = clip(weighted_score / available_weight, -100.0, 100.0)
        return DirectionAssessment(
            horizon=horizon,
            score=score,
            label=self._label(score),
            available_factor_weight=coverage,
            factor_scores=factor_scores,
        )

    def _label(self, score: float) -> DirectionLabel:
        thresholds = self.config.labels
        if score >= thresholds["strong_bullish"]:
            return DirectionLabel.STRONG_BULLISH
        if score >= thresholds["bullish"]:
            return DirectionLabel.BULLISH
        if score <= thresholds["strong_bearish"]:
            return DirectionLabel.STRONG_BEARISH
        if score <= thresholds["bearish"]:
            return DirectionLabel.BEARISH
        return DirectionLabel.NEUTRAL
