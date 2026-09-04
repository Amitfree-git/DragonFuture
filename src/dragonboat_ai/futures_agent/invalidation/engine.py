from __future__ import annotations

import hashlib

from dragonboat_ai.futures_agent.domain.models import (
    DirectionAssessment,
    InvalidationCondition,
    MarketRegime,
    MetricObservation,
)


class InvalidationEngine:
    def build_conditions(
        self,
        *,
        direction: DirectionAssessment,
        regime: MarketRegime,
        metrics: dict[str, MetricObservation],
    ) -> list[InvalidationCondition]:
        if direction.score is None or abs(direction.score) < 25.0:
            return []
        bullish = direction.score > 0
        conditions: list[InvalidationCondition] = []

        if "settlement_vs_ma60" in metrics and metrics["settlement_vs_ma60"].value is not None:
            conditions.append(
                self._condition(
                    direction=direction,
                    code="trend_ma60",
                    description=(
                        "连续两个交易日结算价跌破MA60。"
                        if bullish
                        else "连续两个交易日结算价升破MA60。"
                    ),
                    metric_name="settlement_vs_ma60",
                    operator="cross_below" if bullish else "cross_above",
                    threshold=0.0,
                    current_value=metrics["settlement_vs_ma60"].value,
                    consecutive_bars=2,
                    severity=75.0,
                )
            )

        if "return_20d" in metrics and metrics["return_20d"].normalized_score is not None:
            conditions.append(
                self._condition(
                    direction=direction,
                    code="momentum_reversal",
                    description=(
                        "20日波动率调整收益分数降至-25以下。"
                        if bullish
                        else "20日波动率调整收益分数升至+25以上。"
                    ),
                    metric_name="return_20d",
                    operator="lt" if bullish else "gt",
                    threshold=-25.0 if bullish else 25.0,
                    value_field="normalized_score",
                    current_value=metrics["return_20d"].normalized_score,
                    consecutive_bars=2,
                    severity=55.0,
                )
            )

        if "curve_slope" in metrics and metrics["curve_slope"].value is not None:
            conditions.append(
                self._condition(
                    direction=direction,
                    code="curve_sign_reversal",
                    description=(
                        "期限结构斜率降至零以下。" if bullish else "期限结构斜率升至零以上。"
                    ),
                    metric_name="curve_slope",
                    operator="lt" if bullish else "gt",
                    threshold=0.0,
                    current_value=metrics["curve_slope"].value,
                    consecutive_bars=2,
                    severity=70.0,
                )
            )
        return conditions

    def evaluate(
        self,
        conditions: list[InvalidationCondition],
        metrics: dict[str, MetricObservation],
    ) -> list[InvalidationCondition]:
        evaluated: list[InvalidationCondition] = []
        for condition in conditions:
            metric = metrics.get(condition.metric_name)
            current = getattr(metric, condition.value_field) if metric is not None else None
            triggered = self._triggered(condition.operator, current, condition.threshold)
            evaluated.append(
                condition.model_copy(update={"current_value": current, "triggered": triggered})
            )
        return evaluated

    @staticmethod
    def _triggered(operator: str, value: float | None, threshold: float) -> bool:
        if value is None:
            return False
        if operator in {"lt", "cross_below"}:
            return value < threshold
        if operator == "lte":
            return value <= threshold
        if operator in {"gt", "cross_above"}:
            return value > threshold
        if operator == "gte":
            return value >= threshold
        return False

    @staticmethod
    def _condition(
        *,
        direction: DirectionAssessment,
        code: str,
        description: str,
        metric_name: str,
        operator: str,
        threshold: float,
        current_value: float | None,
        consecutive_bars: int,
        severity: float,
        value_field: str = "value",
    ) -> InvalidationCondition:
        token = f"{direction.horizon.value}|{direction.score}|{code}|{metric_name}"
        condition_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        return InvalidationCondition(
            condition_id=condition_id,
            description=description,
            metric_name=metric_name,
            operator=operator,  # type: ignore[arg-type]
            threshold=threshold,
            value_field=value_field,  # type: ignore[arg-type]
            consecutive_bars=consecutive_bars,
            current_value=current_value,
            severity_if_triggered=severity,
        )
