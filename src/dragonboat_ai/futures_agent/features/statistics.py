from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Sequence

from dragonboat_ai.futures_agent.domain.market_data import DailyBar


def simple_return(values: Sequence[float], periods: int) -> float | None:
    if periods < 1 or len(values) <= periods:
        return None
    start = values[-periods - 1]
    end = values[-1]
    if start == 0:
        return None
    return end / start - 1.0


def log_return(values: Sequence[float], periods: int) -> float | None:
    if periods < 1 or len(values) <= periods:
        return None
    start = values[-periods - 1]
    end = values[-1]
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def log_returns(values: Sequence[float]) -> list[float]:
    output: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0 and current > 0:
            output.append(math.log(current / previous))
    return output


def simple_moving_average(values: Sequence[float], period: int) -> float | None:
    if period < 1 or len(values) < period:
        return None
    return statistics.fmean(values[-period:])


def realized_volatility(
    values: Sequence[float],
    period: int,
    annualization: int = 252,
) -> float | None:
    if period < 2 or len(values) < period + 1:
        return None
    returns = log_returns(values[-period - 1 :])
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(annualization)


def rolling_realized_volatility(
    values: Sequence[float],
    period: int,
    annualization: int = 252,
) -> list[float]:
    output: list[float] = []
    if len(values) < period + 1:
        return output
    for end in range(period + 1, len(values) + 1):
        result = realized_volatility(values[:end], period, annualization)
        if result is not None:
            output.append(result)
    return output


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if period < 1 or len(values) < period + 1:
        return None
    changes = [current - previous for previous, current in zip(values, values[1:], strict=False)]
    window = changes[-period:]
    gains = [change for change in window if change > 0]
    losses = [-change for change in window if change < 0]
    average_gain = statistics.fmean(gains) if gains else 0.0
    average_loss = statistics.fmean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def average_true_range_pct(bars: Sequence[DailyBar], period: int = 20) -> float | None:
    if period < 1 or len(bars) < period + 1:
        return None
    ordered = sorted(bars, key=lambda item: item.trading_date)
    true_ranges: list[float] = []
    for previous, current in zip(ordered[-period - 1 : -1], ordered[-period:], strict=True):
        high = float(current.high)
        low = float(current.low)
        previous_close = float(previous.settlement)
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    latest_price = float(ordered[-1].settlement)
    if latest_price <= 0:
        return None
    return statistics.fmean(true_ranges) / latest_price


def percentile_rank(history: Sequence[float], value: float) -> float | None:
    clean = sorted(item for item in history if math.isfinite(item))
    if not clean:
        return None
    left = bisect.bisect_left(clean, value)
    right = bisect.bisect_right(clean, value)
    # Mid-rank gives stable behaviour for ties.
    rank = (left + right) / 2.0
    return 100.0 * rank / len(clean)


def median_absolute_deviation(values: Sequence[float]) -> float | None:
    clean = [item for item in values if math.isfinite(item)]
    if not clean:
        return None
    med = statistics.median(clean)
    return statistics.median(abs(item - med) for item in clean)


def robust_zscore(value: float, history: Sequence[float], epsilon: float = 1e-12) -> float | None:
    clean = [item for item in history if math.isfinite(item)]
    if len(clean) < 5:
        return None
    med = statistics.median(clean)
    mad = median_absolute_deviation(clean)
    if mad is None:
        return None
    denominator = 1.4826 * mad
    if denominator <= epsilon:
        standard_deviation = statistics.pstdev(clean)
        if standard_deviation <= epsilon:
            return 0.0
        denominator = standard_deviation
    return (value - med) / denominator


def breakout_position(values: Sequence[float], period: int = 120) -> float | None:
    if period < 2 or len(values) < period:
        return None
    window = values[-period:]
    low = min(window)
    high = max(window)
    if math.isclose(high, low):
        return 0.5
    return (values[-1] - low) / (high - low)


def curve_slope(near_price: float, far_price: float, day_gap: int) -> float | None:
    if near_price <= 0 or far_price <= 0 or day_gap <= 0:
        return None
    return math.log(near_price / far_price) * 365.0 / day_gap


def finite_mean(values: Sequence[float | None]) -> float | None:
    clean = [item for item in values if item is not None and math.isfinite(item)]
    return statistics.fmean(clean) if clean else None
