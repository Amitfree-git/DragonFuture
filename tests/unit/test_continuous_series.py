from datetime import date
from decimal import Decimal

from dragonboat_ai.futures_agent.contracts.continuous_series import (
    BackwardAdditiveContinuousSeriesBuilder,
    RawContinuousPoint,
    RollGap,
)


def test_backward_adjustment_removes_roll_jump() -> None:
    points = [
        RawContinuousPoint(date(2026, 8, 31), "RB2610", Decimal("3800")),
        RawContinuousPoint(date(2026, 9, 1), "RB2701", Decimal("3900")),
    ]
    gaps = [
        RollGap(
            effective_date=date(2026, 9, 1),
            from_contract="RB2610",
            to_contract="RB2701",
            from_settlement=Decimal("3800"),
            to_settlement=Decimal("3900"),
        )
    ]
    adjusted = BackwardAdditiveContinuousSeriesBuilder().build(points, gaps)
    assert adjusted[0].adjusted_settlement == Decimal("3900")
    assert adjusted[1].adjusted_settlement == Decimal("3900")
    assert adjusted[1].roll_flag is True
