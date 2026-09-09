from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class StreakState:
    last_session: date | None = None
    streak: int = 0
    last_value: float | None = None
    triggered: bool = False
    status: str = "active"


class InvalidationStateMachine:
    """Track cross and consecutive-bar invalidation without look-ahead or duplicate days."""

    def __init__(self) -> None:
        self._states: dict[str, StreakState] = {}

    def observe(
        self,
        *,
        condition_id: str,
        session_date: date,
        value: float | None,
        operator: str,
        threshold: float,
        consecutive_bars: int = 1,
        previous_session: date | None = None,
    ) -> StreakState:
        state = self._states.setdefault(condition_id, StreakState())
        if state.last_session is not None and session_date <= state.last_session:
            return state
        if previous_session is not None and state.last_session != previous_session:
            state.streak = 0
            state.last_value = None
        if value is None:
            state.last_session = session_date
            state.streak = 0
            state.last_value = None
            state.triggered = False
            state.status = "unknown"
            return state
        crossed = self._cross(operator, state.last_value, value, threshold)
        comparison = self._compare(operator, value, threshold)
        if operator in {"cross_below", "cross_above"}:
            if state.last_value is None:
                triggered = False
                streak = 0
            else:
                triggered = crossed
                streak = state.streak + 1 if triggered else 0
        else:
            triggered = comparison
            streak = state.streak + 1 if triggered else 0
        state.last_session = session_date
        state.last_value = value
        state.streak = streak
        state.triggered = triggered and (operator in {"cross_below", "cross_above"} or streak >= consecutive_bars)
        state.status = "invalidated" if state.triggered else "warning" if state.streak else "active"
        return state

    @staticmethod
    def _compare(operator: str, value: float, threshold: float) -> bool:
        if operator in {"lt", "cross_below"}:
            return value < threshold
        if operator == "lte":
            return value <= threshold
        if operator in {"gt", "cross_above"}:
            return value > threshold
        if operator == "gte":
            return value >= threshold
        return False

    @classmethod
    def _cross(cls, operator: str, previous: float | None, current: float, threshold: float) -> bool:
        if previous is None:
            return False
        if operator == "cross_below":
            return previous >= threshold and current < threshold
        if operator == "cross_above":
            return previous <= threshold and current > threshold
        return False
