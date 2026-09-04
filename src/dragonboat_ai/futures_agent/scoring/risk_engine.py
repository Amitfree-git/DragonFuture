from __future__ import annotations

from dragonboat_ai.futures_agent.domain.market_data import MarketContext
from dragonboat_ai.futures_agent.domain.models import (
    DataQualityAssessment,
    MetricObservation,
    RiskAssessment,
    RiskItem,
)
from dragonboat_ai.futures_agent.domain.enums import RiskLevel
from dragonboat_ai.futures_agent.features.normalization import clip, risk_from_percentile

from .config import ScoringConfig


class RiskEngine:
    _SOFT_WEIGHTS = {
        "volatility_risk": 0.30,
        "liquidity_risk": 0.20,
        "roll_risk": 0.15,
        "price_limit_risk": 0.15,
        "crowding_risk": 0.10,
        "data_quality_risk": 0.10,
    }

    def __init__(self, config: ScoringConfig | None = None) -> None:
        self.config = config or ScoringConfig.default()

    def assess(
        self,
        *,
        context: MarketContext,
        metrics: dict[str, MetricObservation],
        data_quality: DataQualityAssessment,
    ) -> RiskAssessment:
        items: list[RiskItem] = []
        values: dict[str, float] = {}

        vol_percentile = self._value(metrics, "volatility_percentile")
        if vol_percentile is not None:
            severity = risk_from_percentile(vol_percentile)
            values["volatility_risk"] = severity
            items.append(
                RiskItem(
                    risk_code="volatility_risk",
                    severity=severity,
                    description="实现波动率处于较高历史分位。" if severity >= 50 else "波动率风险未处于极端区间。",
                    observed_value=vol_percentile,
                    threshold=self.config.volatility_thresholds["high_percentile"],
                    metric_ids=[metrics["volatility_percentile"].metric_id],
                )
            )

        liquidity = self._value(metrics, "liquidity_quality_score")
        if liquidity is not None:
            severity = clip(100.0 - liquidity, 0.0, 100.0)
            hard = liquidity < self.config.hard_gates["minimum_liquidity_quality"]
            values["liquidity_risk"] = severity
            items.append(
                RiskItem(
                    risk_code="liquidity_risk",
                    severity=max(severity, 85.0) if hard else severity,
                    description="所选合约流动性不足。" if hard else "按成交量、持仓量及品种占比评估流动性。",
                    hard_gate=hard,
                    observed_value=liquidity,
                    threshold=self.config.hard_gates["minimum_liquidity_quality"],
                    metric_ids=[metrics["liquidity_quality_score"].metric_id],
                )
            )

        roll_risk = self._value(metrics, "roll_risk_score")
        if roll_risk is not None:
            values["roll_risk"] = roll_risk
            items.append(
                RiskItem(
                    risk_code="roll_risk",
                    severity=roll_risk,
                    description="根据距离到期日评估移仓和交割风险。",
                    observed_value=float(context.days_to_expiry),
                    threshold=self.config.hard_gates["minimum_days_to_expiry"],
                    metric_ids=[metrics["roll_risk_score"].metric_id],
                )
            )

        price_limit = self._value(metrics, "price_limit_proximity_risk")
        if price_limit is not None:
            hard = price_limit >= 90.0
            values["price_limit_risk"] = price_limit
            items.append(
                RiskItem(
                    risk_code="price_limit_risk",
                    severity=price_limit,
                    description="结算价接近涨跌停边界。" if price_limit >= 60 else "价格距离涨跌停边界尚有空间。",
                    hard_gate=hard,
                    observed_value=price_limit,
                    threshold=90.0,
                    metric_ids=[metrics["price_limit_proximity_risk"].metric_id],
                )
            )

        oi_percentile = self._value(metrics, "open_interest_percentile")
        if oi_percentile is not None:
            crowding = clip((oi_percentile - 80.0) * 5.0, 0.0, 100.0)
            values["crowding_risk"] = crowding
            items.append(
                RiskItem(
                    risk_code="crowding_risk",
                    severity=crowding,
                    description="高持仓分位提示潜在拥挤，但不识别拥挤方向。",
                    observed_value=oi_percentile,
                    threshold=90.0,
                    metric_ids=[metrics["open_interest_percentile"].metric_id],
                )
            )

        data_quality_risk = clip(100.0 - data_quality.overall_score, 0.0, 100.0)
        data_hard = data_quality.overall_score < self.config.hard_gates["minimum_data_quality"]
        values["data_quality_risk"] = data_quality_risk
        items.append(
            RiskItem(
                risk_code="data_quality_risk",
                severity=max(data_quality_risk, 90.0) if data_hard else data_quality_risk,
                description="数据质量不足，禁止形成交易候选。" if data_hard else "数据质量风险可控。",
                hard_gate=data_hard,
                observed_value=data_quality.overall_score,
                threshold=self.config.hard_gates["minimum_data_quality"],
            )
        )

        expiry_hard = context.days_to_expiry < int(self.config.hard_gates["minimum_days_to_expiry"])
        if expiry_hard:
            items.append(
                RiskItem(
                    risk_code="expiry_hard_gate",
                    severity=100.0,
                    description="合约距离到期日过近。",
                    hard_gate=True,
                    observed_value=float(context.days_to_expiry),
                    threshold=self.config.hard_gates["minimum_days_to_expiry"],
                )
            )

        available_weight = sum(self._SOFT_WEIGHTS[name] for name in values)
        soft_risk = (
            sum(self._SOFT_WEIGHTS[name] * value for name, value in values.items()) / available_weight
            if available_weight > 0
            else 0.0
        )
        hard_gate_items = [item for item in items if item.hard_gate]
        hard_gate_risk = max((item.severity for item in hard_gate_items), default=0.0)
        score = clip(max(soft_risk, hard_gate_risk), 0.0, 100.0)
        return RiskAssessment(
            score=score,
            level=self._level(score),
            hard_gate_triggered=bool(hard_gate_items),
            items=items,
        )

    @staticmethod
    def _value(metrics: dict[str, MetricObservation], name: str) -> float | None:
        metric = metrics.get(name)
        return metric.value if metric is not None else None

    @staticmethod
    def _level(score: float) -> RiskLevel:
        if score >= 80.0:
            return RiskLevel.EXTREME
        if score >= 60.0:
            return RiskLevel.HIGH
        if score >= 30.0:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
