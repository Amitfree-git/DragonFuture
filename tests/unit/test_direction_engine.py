from dragonboat_ai.futures_agent.domain.enums import (
    AnalysisHorizon,
    DataStatus,
    DirectionLabel,
    FactorName,
)
from dragonboat_ai.futures_agent.domain.models import FactorAssessment
from dragonboat_ai.futures_agent.scoring.direction_engine import DirectionEngine


def factor(name: FactorName, score: float | None, status: DataStatus = DataStatus.OK) -> FactorAssessment:
    return FactorAssessment(
        factor=name,
        status=status,
        score=score,
        coverage=100 if score is not None else 0,
        confidence=90 if score is not None else 0,
    )


def test_missing_factor_is_not_treated_as_zero() -> None:
    factors = [
        factor(FactorName.TREND, 80),
        factor(FactorName.MOMENTUM, 40),
        factor(FactorName.POSITIONING, 20),
        factor(FactorName.TERM_STRUCTURE, None, DataStatus.MISSING),
    ]
    result = DirectionEngine().assess(AnalysisHorizon.SWING, factors)
    expected = (0.40 * 80 + 0.25 * 40 + 0.15 * 20) / 0.80
    assert result.score == expected
    assert result.available_factor_weight == 80
    assert result.label is DirectionLabel.BULLISH


def test_direction_is_insufficient_below_coverage_threshold() -> None:
    result = DirectionEngine().assess(
        AnalysisHorizon.SWING,
        [factor(FactorName.TREND, 80)],
    )
    assert result.score is None
    assert result.label is DirectionLabel.INSUFFICIENT_DATA
