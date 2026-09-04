from __future__ import annotations

import math


def clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def percentile_to_signed_score(percentile: float) -> float:
    """Map a 0..100 percentile to a bounded -100..100 directional score."""
    return clip(2.0 * percentile - 100.0, -100.0, 100.0)


def tanh_score(z_value: float, scale: float = 2.0) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    return clip(100.0 * math.tanh(z_value / scale), -100.0, 100.0)


def risk_from_percentile(percentile: float, neutral_below: float = 50.0) -> float:
    if percentile <= neutral_below:
        return 0.0
    return clip((percentile - neutral_below) / (100.0 - neutral_below) * 100.0, 0.0, 100.0)
