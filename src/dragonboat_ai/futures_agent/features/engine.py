from __future__ import annotations

import hashlib
import math
import statistics
from datetime import datetime, time, timezone

from dragonboat_ai.futures_agent.domain.enums import DataStatus
from dragonboat_ai.futures_agent.domain.market_data import CurveSnapshot, MarketContext
from dragonboat_ai.futures_agent.domain.models import MetricObservation

from .normalization import clip, percentile_to_signed_score, tanh_score
from .statistics import (
    average_true_range_pct,
    breakout_position,
    curve_slope,
    log_return,
    percentile_rank,
    realized_volatility,
    robust_zscore,
    rolling_realized_volatility,
    rsi,
    simple_moving_average,
    simple_return,
)


class ReferenceFeatureEngine:
    """Pure-Python deterministic daily feature implementation for V1.

    It intentionally computes only market-data features. News, fundamentals,
    weather and discretionary LLM inputs are excluded from this layer.
    """

    FEATURE_SET_VERSION = "futures_features_v1"

    def compute(self, context: MarketContext) -> dict[str, MetricObservation]:
        metrics: dict[str, MetricObservation] = {}
        continuous = sorted(context.continuous_bars, key=lambda item: item.trading_date)
        contract_bars = sorted(context.contract_bars, key=lambda item: item.trading_date)

        prices = [float(item.adjusted_settlement) for item in continuous]
        contract_prices = [float(item.settlement) for item in contract_bars]
        latest_available_at = max(
            [item.available_at for item in continuous]
            + [item.available_at for item in contract_bars],
            default=context.request.as_of,
        )
        latest_date = (
            continuous[-1].trading_date
            if continuous
            else contract_bars[-1].trading_date
            if contract_bars
            else context.request.as_of.date()
        )
        observation_time = datetime.combine(latest_date, time.min, tzinfo=timezone.utc)

        rv20 = realized_volatility(prices, 20)
        rv60 = realized_volatility(prices, 60)
        daily_vol = rv20 / math.sqrt(252.0) if rv20 and rv20 > 0 else None

        for period in (5, 20, 60, 120):
            value = simple_return(prices, period)
            log_value = log_return(prices, period)
            normalized = None
            if log_value is not None and daily_vol and daily_vol > 0:
                normalized = tanh_score(log_value / (daily_vol * math.sqrt(period)), scale=1.5)
            metrics[f"return_{period}d"] = self._observation(
                context=context,
                name=f"return_{period}d",
                value=value,
                unit="ratio",
                normalized_score=normalized,
                observation_time=observation_time,
                available_at=latest_available_at,
                lookback=period,
                source="continuous_back_adjusted",
                sample_size=len(prices),
                minimum_sample=period + 1,
            )

        ma20 = simple_moving_average(prices, 20)
        ma60 = simple_moving_average(prices, 60)
        latest_price = prices[-1] if prices else None
        atr_pct = average_true_range_pct(contract_bars, 20)
        fallback_range = daily_vol * math.sqrt(5.0) if daily_vol else None
        range_unit = atr_pct or fallback_range

        settlement_vs_ma20 = self._relative_distance(latest_price, ma20)
        settlement_vs_ma60 = self._relative_distance(latest_price, ma60)
        extension_atr = (
            settlement_vs_ma20 / range_unit
            if settlement_vs_ma20 is not None and range_unit and range_unit > 0
            else None
        )

        metrics["settlement_vs_ma20"] = self._observation(
            context=context,
            name="settlement_vs_ma20",
            value=settlement_vs_ma20,
            unit="ratio",
            normalized_score=tanh_score(extension_atr, 2.0) if extension_atr is not None else None,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=20,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=20,
        )
        metrics["settlement_vs_ma60"] = self._observation(
            context=context,
            name="settlement_vs_ma60",
            value=settlement_vs_ma60,
            unit="ratio",
            normalized_score=(
                tanh_score(settlement_vs_ma60 / (daily_vol * math.sqrt(20.0)), 2.0)
                if settlement_vs_ma60 is not None and daily_vol and daily_vol > 0
                else None
            ),
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=60,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=60,
        )
        metrics["extension_atr"] = self._observation(
            context=context,
            name="extension_atr",
            value=extension_atr,
            unit="atr",
            normalized_score=tanh_score(extension_atr, 2.0) if extension_atr is not None else None,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=20,
            source="continuous_back_adjusted+selected_contract",
            sample_size=min(len(prices), len(contract_bars)),
            minimum_sample=21,
        )

        ma_structure = self._ma_structure(prices, ma20, ma60, daily_vol)
        metrics["ma_structure"] = self._observation(
            context=context,
            name="ma_structure",
            value=ma_structure,
            unit="score",
            normalized_score=ma_structure,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=60,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=65,
        )

        breakout = breakout_position(prices, 120)
        metrics["breakout_position_120d"] = self._observation(
            context=context,
            name="breakout_position_120d",
            value=breakout,
            unit="ratio",
            normalized_score=clip(200.0 * (breakout - 0.5), -100.0, 100.0) if breakout is not None else None,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=120,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=120,
        )

        rsi14 = rsi(prices, 14)
        metrics["rsi_14"] = self._observation(
            context=context,
            name="rsi_14",
            value=rsi14,
            unit="index",
            normalized_score=clip((rsi14 - 50.0) * 2.0, -100.0, 100.0) if rsi14 is not None else None,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=14,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=15,
        )

        return5 = metrics["return_5d"].value
        return20 = metrics["return_20d"].value
        acceleration = return5 - return20 / 4.0 if return5 is not None and return20 is not None else None
        acceleration_score = None
        if acceleration is not None and daily_vol and daily_vol > 0:
            acceleration_score = tanh_score(acceleration / (daily_vol * math.sqrt(5.0)), 1.5)
        metrics["momentum_acceleration"] = self._observation(
            context=context,
            name="momentum_acceleration",
            value=acceleration,
            unit="ratio",
            normalized_score=acceleration_score,
            observation_time=observation_time,
            available_at=latest_available_at,
            lookback=20,
            source="continuous_back_adjusted",
            sample_size=len(prices),
            minimum_sample=21,
        )

        self._add_positioning_metrics(
            metrics=metrics,
            context=context,
            contract_prices=contract_prices,
            observation_time=observation_time,
            available_at=latest_available_at,
            daily_vol=daily_vol,
        )
        self._add_curve_metrics(metrics, context)
        self._add_volatility_metrics(
            metrics,
            context,
            prices,
            rv20,
            rv60,
            observation_time,
            latest_available_at,
        )
        self._add_liquidity_metrics(metrics, context, observation_time, latest_available_at)
        self._add_roll_and_limit_metrics(metrics, context, observation_time, latest_available_at)
        return metrics

    def _add_positioning_metrics(
        self,
        metrics: dict[str, MetricObservation],
        context: MarketContext,
        contract_prices: list[float],
        observation_time: datetime,
        available_at: datetime,
        daily_vol: float | None,
    ) -> None:
        bars = sorted(context.contract_bars, key=lambda item: item.trading_date)
        price_return_5d = simple_return(contract_prices, 5)
        price_score = None
        if price_return_5d is not None and daily_vol and daily_vol > 0:
            price_score = tanh_score(price_return_5d / (daily_vol * math.sqrt(5.0)), 1.5)

        oi_change = None
        if len(bars) >= 6 and bars[-6].open_interest > 0:
            oi_change = bars[-1].open_interest / bars[-6].open_interest - 1.0
        oi_score = 100.0 * math.tanh(oi_change / 0.05) if oi_change is not None else None
        oi_score = clip(oi_score, -100.0, 100.0) if oi_score is not None else None

        volumes = [float(bar.volume) for bar in bars]
        volume_zscore = None
        volume_score = None
        if len(volumes) >= 21:
            volume_zscore = robust_zscore(volumes[-1], volumes[-61:-1])
            volume_score = tanh_score(volume_zscore) if volume_zscore is not None else None

        positioning = None
        if price_score is not None and oi_score is not None:
            direction = 1.0 if price_score > 0 else -1.0 if price_score < 0 else 0.0
            if oi_change is not None and oi_change >= 0:
                positioning = direction * (0.70 * abs(price_score) + 0.30 * abs(oi_score))
            else:
                positioning = direction * (0.45 * abs(price_score) + 0.10 * abs(oi_score))
            if volume_score is not None:
                positioning = 0.90 * positioning + 0.10 * direction * max(volume_score, 0.0)
            positioning = clip(positioning, -100.0, 100.0)

        common = dict(
            context=context,
            observation_time=observation_time,
            available_at=available_at,
            source="selected_contract",
            sample_size=len(bars),
        )
        metrics["contract_return_5d"] = self._observation(
            name="contract_return_5d",
            value=price_return_5d,
            unit="ratio",
            normalized_score=price_score,
            lookback=5,
            minimum_sample=6,
            **common,
        )
        metrics["oi_change_5d"] = self._observation(
            name="oi_change_5d",
            value=oi_change,
            unit="ratio",
            normalized_score=oi_score,
            lookback=5,
            minimum_sample=6,
            **common,
        )
        metrics["volume_zscore_20d"] = self._observation(
            name="volume_zscore_20d",
            value=volume_zscore,
            unit="zscore",
            normalized_score=volume_score,
            lookback=20,
            minimum_sample=21,
            **common,
        )
        metrics["positioning_composite"] = self._observation(
            name="positioning_composite",
            value=positioning,
            unit="score",
            normalized_score=positioning,
            lookback=5,
            minimum_sample=6,
            **common,
        )

    def _add_curve_metrics(
        self,
        metrics: dict[str, MetricObservation],
        context: MarketContext,
    ) -> None:
        current = context.current_curve
        current_slope = self._snapshot_slope(current)
        historical = sorted(
            [curve for curve in context.historical_curves if current is None or curve.trading_date < current.trading_date],
            key=lambda item: item.trading_date,
        )
        historical_slopes = [value for value in (self._snapshot_slope(item) for item in historical) if value is not None]
        current_percentile = percentile_rank(historical_slopes, current_slope) if current_slope is not None else None
        current_zscore = robust_zscore(current_slope, historical_slopes) if current_slope is not None else None
        # Preserve the economic sign of the curve: backwardation is positive
        # and contango is negative. Historical z-score remains metadata; the
        # separate change feature captures strengthening or weakening.
        slope_score = tanh_score(current_slope / 0.10) if current_slope is not None else None

        slope_change = None
        if current_slope is not None and len(historical_slopes) >= 20:
            slope_change = current_slope - historical_slopes[-20]
        historical_changes = [
            historical_slopes[index] - historical_slopes[index - 20]
            for index in range(20, len(historical_slopes))
        ]
        change_zscore = robust_zscore(slope_change, historical_changes) if slope_change is not None else None
        change_score = (
            tanh_score(change_zscore)
            if change_zscore is not None
            else tanh_score(slope_change / 0.05)
            if slope_change is not None
            else None
        )

        curvature = self._snapshot_curvature(current)
        historical_curvatures = [
            value for value in (self._snapshot_curvature(item) for item in historical) if value is not None
        ]
        curvature_zscore = robust_zscore(curvature, historical_curvatures) if curvature is not None else None
        curvature_score = (
            tanh_score(curvature_zscore)
            if curvature_zscore is not None
            else tanh_score(curvature / 0.05)
            if curvature is not None
            else None
        )

        available_at = current.available_at if current else context.request.as_of
        observation_time = (
            current.observed_at
            if current
            else datetime.combine(context.request.as_of.date(), time.min, tzinfo=timezone.utc)
        )
        sample_size = len(historical_slopes)
        common = dict(
            context=context,
            observation_time=observation_time,
            available_at=available_at,
            source="real_contract_curve",
            sample_size=sample_size,
        )
        metrics["curve_slope"] = self._observation(
            name="curve_slope",
            value=current_slope,
            unit="annualized_log_spread",
            normalized_score=slope_score,
            percentile=current_percentile,
            zscore=current_zscore,
            lookback=max(sample_size, 1),
            minimum_sample=1,
            **common,
        )
        metrics["curve_slope_change_20d"] = self._observation(
            name="curve_slope_change_20d",
            value=slope_change,
            unit="annualized_log_spread",
            normalized_score=change_score,
            zscore=change_zscore,
            lookback=20,
            minimum_sample=20,
            **common,
        )
        metrics["curve_curvature"] = self._observation(
            name="curve_curvature",
            value=curvature,
            unit="annualized_log_spread",
            normalized_score=curvature_score,
            zscore=curvature_zscore,
            lookback=max(sample_size, 1),
            minimum_sample=1,
            **common,
        )

    def _add_volatility_metrics(
        self,
        metrics: dict[str, MetricObservation],
        context: MarketContext,
        prices: list[float],
        rv20: float | None,
        rv60: float | None,
        observation_time: datetime,
        available_at: datetime,
    ) -> None:
        vol_history = rolling_realized_volatility(prices, 20)
        reference_history = vol_history[:-1] if len(vol_history) > 1 else []
        percentile = percentile_rank(reference_history, rv20) if rv20 is not None else None
        common = dict(
            context=context,
            observation_time=observation_time,
            available_at=available_at,
            source="continuous_back_adjusted",
            sample_size=len(prices),
        )
        metrics["realized_vol_20d"] = self._observation(
            name="realized_vol_20d",
            value=rv20,
            unit="annualized_ratio",
            normalized_score=None,
            percentile=percentile,
            lookback=20,
            minimum_sample=21,
            **common,
        )
        metrics["realized_vol_60d"] = self._observation(
            name="realized_vol_60d",
            value=rv60,
            unit="annualized_ratio",
            normalized_score=None,
            lookback=60,
            minimum_sample=61,
            **common,
        )
        metrics["volatility_percentile"] = self._observation(
            name="volatility_percentile",
            value=percentile,
            unit="percentile",
            normalized_score=percentile_to_signed_score(percentile) if percentile is not None else None,
            percentile=percentile,
            lookback=max(len(reference_history), 1),
            minimum_sample=20,
            **common,
        )

    def _add_liquidity_metrics(
        self,
        metrics: dict[str, MetricObservation],
        context: MarketContext,
        observation_time: datetime,
        available_at: datetime,
    ) -> None:
        bars = sorted(context.contract_bars, key=lambda item: item.trading_date)
        latest = bars[-1] if bars else None
        volume_history = [float(item.volume) for item in bars[:-1]]
        oi_history = [float(item.open_interest) for item in bars[:-1]]
        volume_percentile = percentile_rank(volume_history[-252:], float(latest.volume)) if latest else None
        oi_percentile = percentile_rank(oi_history[-252:], float(latest.open_interest)) if latest else None

        volume_share = None
        oi_share = None
        if context.current_curve and context.current_curve.points:
            total_volume = sum(max(point.volume, 0) for point in context.current_curve.points)
            total_oi = sum(max(point.open_interest, 0) for point in context.current_curve.points)
            selected = next(
                (point for point in context.current_curve.points if point.contract == context.selected_contract),
                None,
            )
            if selected and total_volume > 0:
                volume_share = selected.volume / total_volume
            if selected and total_oi > 0:
                oi_share = selected.open_interest / total_oi

        components = [
            volume_percentile,
            oi_percentile,
            volume_share * 100.0 if volume_share is not None else None,
            oi_share * 100.0 if oi_share is not None else None,
        ]
        clean_components = [item for item in components if item is not None]
        liquidity_quality = statistics.fmean(clean_components) if clean_components else None

        common = dict(
            context=context,
            observation_time=observation_time,
            available_at=available_at,
            source="selected_contract+real_contract_curve",
            sample_size=len(bars),
        )
        for name, value, unit in (
            ("volume_percentile", volume_percentile, "percentile"),
            ("open_interest_percentile", oi_percentile, "percentile"),
            ("contract_volume_share", volume_share, "ratio"),
            ("contract_open_interest_share", oi_share, "ratio"),
        ):
            metrics[name] = self._observation(
                name=name,
                value=value,
                unit=unit,
                normalized_score=(
                    percentile_to_signed_score(value)
                    if value is not None and unit == "percentile"
                    else clip(200.0 * value - 100.0, -100.0, 100.0)
                    if value is not None
                    else None
                ),
                lookback=252,
                minimum_sample=20,
                **common,
            )
        metrics["liquidity_quality_score"] = self._observation(
            name="liquidity_quality_score",
            value=liquidity_quality,
            unit="score",
            normalized_score=(
                clip(2.0 * liquidity_quality - 100.0, -100.0, 100.0)
                if liquidity_quality is not None
                else None
            ),
            lookback=252,
            minimum_sample=20,
            **common,
        )

    def _add_roll_and_limit_metrics(
        self,
        metrics: dict[str, MetricObservation],
        context: MarketContext,
        observation_time: datetime,
        available_at: datetime,
    ) -> None:
        dte = float(context.days_to_expiry)
        if dte <= 5:
            roll_risk = 100.0
        elif dte <= 10:
            roll_risk = 80.0
        elif dte <= 20:
            roll_risk = 50.0
        elif dte <= 40:
            roll_risk = 20.0
        else:
            roll_risk = 0.0

        common = dict(
            context=context,
            observation_time=observation_time,
            available_at=available_at,
            source="contract_metadata",
            sample_size=1,
            minimum_sample=1,
        )
        metrics["days_to_expiry"] = self._observation(
            name="days_to_expiry",
            value=dte,
            unit="days",
            normalized_score=None,
            lookback=1,
            **common,
        )
        metrics["roll_risk_score"] = self._observation(
            name="roll_risk_score",
            value=roll_risk,
            unit="risk_score",
            normalized_score=clip(roll_risk * 2.0 - 100.0, -100.0, 100.0),
            lookback=1,
            **common,
        )

        latest = max(context.contract_bars, key=lambda item: item.trading_date, default=None)
        proximity = None
        if latest:
            price = float(latest.settlement)
            distances: list[float] = []
            if latest.upper_limit is not None and float(latest.upper_limit) > price > 0:
                distances.append((float(latest.upper_limit) - price) / price)
            if latest.lower_limit is not None and price > float(latest.lower_limit) > 0:
                distances.append((price - float(latest.lower_limit)) / price)
            if distances:
                nearest = min(distances)
                proximity = clip((0.03 - nearest) / 0.03 * 100.0, 0.0, 100.0)
        metrics["price_limit_proximity_risk"] = self._observation(
            name="price_limit_proximity_risk",
            value=proximity,
            unit="risk_score",
            normalized_score=clip(proximity * 2.0 - 100.0, -100.0, 100.0) if proximity is not None else None,
            lookback=1,
            **common,
        )

    @staticmethod
    def _relative_distance(price: float | None, reference: float | None) -> float | None:
        if price is None or reference is None or reference == 0:
            return None
        return price / reference - 1.0

    @staticmethod
    def _ma_structure(
        prices: list[float],
        ma20: float | None,
        ma60: float | None,
        daily_vol: float | None,
    ) -> float | None:
        if len(prices) < 65 or ma20 is None or ma60 is None or not daily_vol:
            return None
        latest = prices[-1]
        previous_ma20 = statistics.fmean(prices[-25:-5])
        base = 0.0
        base += 30.0 if latest > ma20 else -30.0
        base += 30.0 if ma20 > ma60 else -30.0
        slope = math.log(ma20 / previous_ma20) if ma20 > 0 and previous_ma20 > 0 else 0.0
        slope_score = tanh_score(slope / (daily_vol * math.sqrt(5.0)), 1.5)
        return clip(base + 0.40 * slope_score, -100.0, 100.0)

    @staticmethod
    def _snapshot_slope(snapshot: CurveSnapshot | None) -> float | None:
        if snapshot is None:
            return None
        points = sorted((point for point in snapshot.points if point.days_to_expiry > 0), key=lambda item: item.days_to_expiry)
        if len(points) < 2:
            return None
        near, far = points[0], points[1]
        return curve_slope(float(near.settlement), float(far.settlement), far.days_to_expiry - near.days_to_expiry)

    @staticmethod
    def _snapshot_curvature(snapshot: CurveSnapshot | None) -> float | None:
        if snapshot is None:
            return None
        points = sorted((point for point in snapshot.points if point.days_to_expiry > 0), key=lambda item: item.days_to_expiry)
        if len(points) < 3:
            return None
        first, second, third = points[:3]
        front = curve_slope(
            float(first.settlement),
            float(second.settlement),
            second.days_to_expiry - first.days_to_expiry,
        )
        back = curve_slope(
            float(second.settlement),
            float(third.settlement),
            third.days_to_expiry - second.days_to_expiry,
        )
        if front is None or back is None:
            return None
        return front - back

    @staticmethod
    def _quality(sample_size: int, minimum_sample: int, value: float | None) -> tuple[DataStatus, float]:
        if value is None:
            return DataStatus.MISSING, 0.0
        if sample_size < minimum_sample:
            return DataStatus.INSUFFICIENT, clip(sample_size / max(minimum_sample, 1) * 100.0, 0.0, 100.0)
        quality = clip(70.0 + 30.0 * min(sample_size / max(minimum_sample * 2, 1), 1.0), 0.0, 100.0)
        return DataStatus.OK, quality

    def _observation(
        self,
        *,
        context: MarketContext,
        name: str,
        value: float | None,
        unit: str | None,
        normalized_score: float | None,
        observation_time: datetime,
        available_at: datetime,
        lookback: int,
        source: str,
        sample_size: int,
        minimum_sample: int,
        percentile: float | None = None,
        zscore: float | None = None,
    ) -> MetricObservation:
        status, quality = self._quality(sample_size, minimum_sample, value)
        token = f"{context.symbol}|{context.selected_contract}|{context.request.as_of.isoformat()}|{name}"
        metric_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        return MetricObservation(
            metric_id=metric_id,
            name=name,
            value=value,
            unit=unit,
            normalized_score=clip(normalized_score, -100.0, 100.0) if normalized_score is not None else None,
            observation_time=observation_time,
            available_at=available_at,
            lookback=max(lookback, 1),
            percentile=clip(percentile, 0.0, 100.0) if percentile is not None else None,
            zscore=zscore,
            source=source,
            quality_score=quality,
            status=status,
        )
