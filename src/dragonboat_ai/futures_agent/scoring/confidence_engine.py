from __future__ import annotations

import math
from datetime import datetime

from dragonboat_ai.futures_agent.domain.enums import DataStatus
from dragonboat_ai.futures_agent.domain.models import (
    ConfidenceAssessment,
    DataQualityAssessment,
    DirectionAssessment,
    FactorAssessment,
    MetricObservation,
)
from dragonboat_ai.futures_agent.features.normalization import clip

from .config import ScoringConfig


class ConfidenceEngine:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig.default()

    def assess(
        self,
        *,
        as_of: datetime,
        factors: list[FactorAssessment],
        direction: DirectionAssessment,
        metrics: dict[str, MetricObservation],
        data_quality: DataQualityAssessment,
        historical_calibration: float | None = None,
    ) -> ConfidenceAssessment:
        coverage = direction.available_factor_weight
        freshness = self._freshness(as_of, metrics)
        agreement = self._agreement(direction, factors)
        components: dict[str, float | None] = {
            "coverage": coverage,
            "freshness": freshness,
            "agreement": agreement,
            "data_quality": data_quality.overall_score,
            "historical_calibration": historical_calibration,
        }
        weights = self.config.confidence_weights
        available_weight = sum(weights[name] for name, value in components.items() if value is not None)
        score = (
            sum(weights[name] * float(value) for name, value in components.items() if value is not None)
            / available_weight
            if available_weight > 0
            else 0.0
        )
        return ConfidenceAssessment(
            score=clip(score, 0.0, 100.0),
            data_coverage=coverage,
            freshness=freshness,
            factor_agreement=agreement,
            data_quality=data_quality.overall_score,
            historical_calibration=historical_calibration,
        )

    @staticmethod
    def _freshness(as_of: datetime, metrics: dict[str, MetricObservation]) -> float:
        valid = [
            metric
            for metric in metrics.values()
            if metric.status in {DataStatus.OK, DataStatus.PARTIAL} and metric.value is not None
        ]
        if not valid:
            return 0.0
        values: list[float] = []
        for metric in valid:
            age_days = max((as_of - metric.available_at).total_seconds() / 86400.0, 0.0)
            # Daily features retain high freshness over weekends but decay materially after one week.
            values.append(100.0 * math.exp(-age_days / 10.0))
        return clip(sum(values) / len(values), 0.0, 100.0)

    def _agreement(
        self,
        direction: DirectionAssessment,
        factors: list[FactorAssessment],
    ) -> float:
        if direction.score is None or abs(direction.score) < 1e-12:
            return 50.0
        weights = self.config.direction_weights[direction.horizon.value]
        available = 0.0
        opposing = 0.0
        direction_sign = 1.0 if direction.score > 0 else -1.0
        for factor in factors:
            weight = weights.get(factor.factor.value, 0.0)
            if factor.score is None or factor.status not in {DataStatus.OK, DataStatus.PARTIAL}:
                continue
            available += weight
            if abs(factor.score) >= 20.0 and factor.score * direction_sign < 0:
                opposing += weight
        if available <= 0:
            return 0.0
        return clip(100.0 * (1.0 - opposing / available), 0.0, 100.0)
