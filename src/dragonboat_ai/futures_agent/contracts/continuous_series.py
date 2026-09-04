from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RawContinuousPoint:
    trading_date: date
    source_contract: str
    settlement: Decimal


@dataclass(frozen=True, slots=True)
class RollGap:
    effective_date: date
    from_contract: str
    to_contract: str
    from_settlement: Decimal
    to_settlement: Decimal

    @property
    def additive_gap(self) -> Decimal:
        return self.to_settlement - self.from_settlement


@dataclass(frozen=True, slots=True)
class AdjustedContinuousPoint:
    trading_date: date
    source_contract: str
    raw_settlement: Decimal
    adjusted_settlement: Decimal
    cumulative_adjustment: Decimal
    roll_flag: bool


class BackwardAdditiveContinuousSeriesBuilder:
    """Build a backward-additive series while retaining source-contract lineage."""

    def build(
        self,
        points: list[RawContinuousPoint],
        roll_gaps: list[RollGap],
    ) -> list[AdjustedContinuousPoint]:
        gaps = sorted(roll_gaps, key=lambda item: item.effective_date)
        output: list[AdjustedContinuousPoint] = []
        for point in sorted(points, key=lambda item: item.trading_date):
            adjustment = sum(
                (gap.additive_gap for gap in gaps if point.trading_date < gap.effective_date),
                Decimal("0"),
            )
            output.append(
                AdjustedContinuousPoint(
                    trading_date=point.trading_date,
                    source_contract=point.source_contract,
                    raw_settlement=point.settlement,
                    adjusted_settlement=point.settlement + adjustment,
                    cumulative_adjustment=adjustment,
                    roll_flag=any(gap.effective_date == point.trading_date for gap in gaps),
                )
            )
        return output
