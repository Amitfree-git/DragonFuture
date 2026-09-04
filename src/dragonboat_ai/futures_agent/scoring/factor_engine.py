from __future__ import annotations

import hashlib
from dataclasses import dataclass

from dragonboat_ai.futures_agent.domain.enums import (
    DataStatus,
    EvidenceKind,
    FactorName,
    Stance,
)
from dragonboat_ai.futures_agent.domain.market_data import MarketContext
from dragonboat_ai.futures_agent.domain.models import (
    Evidence,
    FactorAssessment,
    FeatureContribution,
    MetricObservation,
)
from dragonboat_ai.futures_agent.features.normalization import clip


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    weight: float


class DeterministicFactorEngine:
    """Aggregate normalized features into auditable directional factors."""

    _DEFINITIONS: dict[FactorName, tuple[FeatureSpec, ...]] = {
        FactorName.TREND: (
            FeatureSpec("return_20d", 0.30),
            FeatureSpec("return_60d", 0.30),
            FeatureSpec("return_120d", 0.15),
            FeatureSpec("ma_structure", 0.15),
            FeatureSpec("breakout_position_120d", 0.10),
        ),
        FactorName.MOMENTUM: (
            FeatureSpec("return_5d", 0.30),
            FeatureSpec("return_20d", 0.30),
            FeatureSpec("rsi_14", 0.20),
            FeatureSpec("momentum_acceleration", 0.20),
        ),
        FactorName.POSITIONING: (
            # Volume is already used inside positioning_composite only as a
            # confirmation of the observed price direction. Raw high/low
            # volume is not independently bullish or bearish.
            FeatureSpec("positioning_composite", 1.00),
        ),
        FactorName.TERM_STRUCTURE: (
            FeatureSpec("curve_slope", 0.50),
            FeatureSpec("curve_slope_change_20d", 0.30),
            FeatureSpec("curve_curvature", 0.20),
        ),
    }

    _MINIMUM_COVERAGE: dict[FactorName, float] = {
        FactorName.TREND: 0.60,
        FactorName.MOMENTUM: 0.70,
        FactorName.POSITIONING: 0.80,
        FactorName.TERM_STRUCTURE: 0.50,
    }

    _CLAIMS: dict[str, str] = {
        "return_5d": "短期价格收益",
        "return_20d": "20日价格收益",
        "return_60d": "60日价格收益",
        "return_120d": "120日价格收益",
        "ma_structure": "均线结构与斜率",
        "breakout_position_120d": "价格在120日区间中的位置",
        "rsi_14": "14日RSI",
        "momentum_acceleration": "短期动量相对中期动量的加速度",
        "positioning_composite": "价格与持仓变化的组合结构",
        "curve_slope": "近远月年化期限结构斜率",
        "curve_slope_change_20d": "期限结构20日变化",
        "curve_curvature": "期限结构曲率",
    }

    def score(
        self,
        context: MarketContext,
        metrics: dict[str, MetricObservation],
    ) -> tuple[list[FactorAssessment], list[Evidence]]:
        factors: list[FactorAssessment] = []
        evidence: list[Evidence] = []
        for factor, specs in self._DEFINITIONS.items():
            assessment, factor_evidence = self._score_factor(context, factor, specs, metrics)
            factors.append(assessment)
            evidence.extend(factor_evidence)
        return factors, evidence

    def _score_factor(
        self,
        context: MarketContext,
        factor: FactorName,
        specs: tuple[FeatureSpec, ...],
        metrics: dict[str, MetricObservation],
    ) -> tuple[FactorAssessment, list[Evidence]]:
        available: list[tuple[FeatureSpec, MetricObservation]] = []
        total_weight = sum(spec.weight for spec in specs)
        for spec in specs:
            metric = metrics.get(spec.name)
            if (
                metric is not None
                and metric.normalized_score is not None
                and metric.status in {DataStatus.OK, DataStatus.PARTIAL}
            ):
                available.append((spec, metric))

        available_weight = sum(spec.weight for spec, _ in available)
        coverage_ratio = available_weight / total_weight if total_weight else 0.0
        coverage = clip(coverage_ratio * 100.0, 0.0, 100.0)
        minimum = self._MINIMUM_COVERAGE[factor]

        if not available:
            return (
                FactorAssessment(
                    factor=factor,
                    status=DataStatus.MISSING,
                    score=None,
                    coverage=0.0,
                    confidence=0.0,
                    warnings=["No valid normalized feature is available."],
                ),
                [],
            )

        if coverage_ratio < minimum:
            return (
                FactorAssessment(
                    factor=factor,
                    status=DataStatus.INSUFFICIENT,
                    score=None,
                    coverage=coverage,
                    confidence=coverage,
                    warnings=[
                        f"Feature coverage {coverage_ratio:.2%} is below the required {minimum:.2%}."
                    ],
                ),
                [],
            )

        raw_score = sum(spec.weight * float(metric.normalized_score) for spec, metric in available)
        score = clip(raw_score / available_weight, -100.0, 100.0)
        average_quality = sum(spec.weight * metric.quality_score for spec, metric in available) / available_weight
        confidence = clip(coverage_ratio * average_quality, 0.0, 100.0)
        status = DataStatus.OK if coverage_ratio >= 0.999 else DataStatus.PARTIAL

        contributions: list[FeatureContribution] = []
        factor_evidence: list[Evidence] = []
        for spec, metric in available:
            effective_weight = spec.weight / available_weight
            contribution = effective_weight * float(metric.normalized_score)
            contributions.append(
                FeatureContribution(
                    feature_name=spec.name,
                    feature_score=float(metric.normalized_score),
                    weight=effective_weight,
                    weighted_contribution=contribution,
                    metric_ids=[metric.metric_id],
                )
            )
            factor_evidence.append(self._evidence(context, factor, spec.name, metric))

        warnings: list[str] = []
        if status is DataStatus.PARTIAL:
            missing = [spec.name for spec in specs if spec.name not in {item[0].name for item in available}]
            warnings.append(f"Missing optional features: {', '.join(missing)}")

        return (
            FactorAssessment(
                factor=factor,
                status=status,
                score=score,
                coverage=coverage,
                confidence=confidence,
                contributions=contributions,
                evidence_ids=[item.evidence_id for item in factor_evidence],
                warnings=warnings,
            ),
            factor_evidence,
        )

    def _evidence(
        self,
        context: MarketContext,
        factor: FactorName,
        feature_name: str,
        metric: MetricObservation,
    ) -> Evidence:
        score = float(metric.normalized_score or 0.0)
        stance = Stance.BULLISH if score >= 15.0 else Stance.BEARISH if score <= -15.0 else Stance.NEUTRAL
        kind = EvidenceKind.INFERENCE if factor is FactorName.POSITIONING else EvidenceKind.FACT
        direction_text = "偏多" if stance is Stance.BULLISH else "偏空" if stance is Stance.BEARISH else "中性"
        claim = f"{self._CLAIMS.get(feature_name, feature_name)}对当前方向的证据为{direction_text}。"
        reasoning = None
        if factor is FactorName.POSITIONING:
            reasoning = "价格与持仓量的组合只能支持头寸结构推断，不能识别具体交易方的主动行为。"
        token = f"{context.input_data_hash}|{factor.value}|{feature_name}|{metric.metric_id}"
        evidence_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        return Evidence(
            evidence_id=evidence_id,
            factor=factor,
            stance=stance,
            kind=kind,
            strength=clip(abs(score), 0.0, 100.0),
            claim=claim,
            metric_ids=[metric.metric_id],
            reasoning=reasoning,
        )
