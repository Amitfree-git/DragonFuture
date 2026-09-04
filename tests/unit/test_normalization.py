import pytest

from dragonboat_ai.futures_agent.features.normalization import (
    percentile_to_signed_score,
    tanh_score,
)
from dragonboat_ai.futures_agent.features.statistics import percentile_rank, robust_zscore


def test_percentile_score_mapping() -> None:
    assert percentile_to_signed_score(95) == 90
    assert percentile_to_signed_score(50) == 0
    assert percentile_to_signed_score(5) == -90


def test_percentile_rank_is_monotonic() -> None:
    history = [1, 2, 3, 4, 5]
    assert percentile_rank(history, 4) > percentile_rank(history, 2)


def test_robust_zscore_resists_single_outlier() -> None:
    history = [9.8, 9.9, 10.0, 10.1, 10.2, 1000.0]
    result = robust_zscore(10.2, history)
    assert result is not None
    assert result < 3.0


def test_tanh_score_is_bounded() -> None:
    assert tanh_score(1_000) == pytest.approx(100.0)
    assert tanh_score(-1_000) == pytest.approx(-100.0)
