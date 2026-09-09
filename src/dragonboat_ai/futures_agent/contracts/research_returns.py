from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dragonboat_ai.futures_agent.contracts.calendar import ExchangeCalendar
from dragonboat_ai.futures_agent.contracts.continuous_series import RawContinuousPoint, RollGap


@dataclass(frozen=True, slots=True)
class ReturnIndexPoint:
    trading_date: date
    source_contract: str
    index_value: Decimal | None


def same_contract_return_index(
    points: list[RawContinuousPoint],
    roll_gaps: list[RollGap],
    *,
    previous_settlements: dict[tuple[date, str], Decimal] | None = None,
    calendar: ExchangeCalendar | None = None,
) -> list[ReturnIndexPoint]:
    """Chain returns using today's selected contract on both sides of each ratio.

    On a roll, the denominator must be the incoming contract's prior settlement.
    A missing observation or nonpositive price breaks the chain; it is never
    replaced by a fabricated zero return. The next valid segment starts at 100.
    """
    output: list[ReturnIndexPoint] = []
    index: Decimal | None = None
    previous: RawContinuousPoint | None = None
    for point in sorted(points, key=lambda item: item.trading_date):
        value = point.settlement
        consecutive = previous is not None and (
            calendar is None or calendar.next_trading_day(previous.trading_date) == point.trading_date
        )
        if not value.is_finite() or value <= 0:
            index = None
        elif previous is None or not consecutive or index is None:
            index = Decimal("100")
        else:
            denominator = (previous_settlements or {}).get((point.trading_date, point.source_contract))
            if denominator is None and previous.source_contract == point.source_contract:
                denominator = previous.settlement
            if denominator is None or not denominator.is_finite() or denominator <= 0:
                index = None
            else:
                index *= value / denominator
        # The first bar following a missing exchange session is explicitly invalid.
        if previous is not None and not consecutive:
            index = None
        output.append(ReturnIndexPoint(point.trading_date, point.source_contract, index))
        previous = point
    return output
