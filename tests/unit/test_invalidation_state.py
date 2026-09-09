from datetime import date

from dragonboat_ai.futures_agent.invalidation.state import InvalidationStateMachine


def test_cross_requires_previous_observation() -> None:
    machine = InvalidationStateMachine()
    first = machine.observe(
        condition_id="trend_ma60",
        session_date=date(2026, 9, 1),
        value=-0.01,
        operator="cross_below",
        threshold=0.0,
    )
    assert first.triggered is False
    second = machine.observe(
        condition_id="trend_ma60",
        session_date=date(2026, 9, 2),
        value=-0.02,
        operator="cross_below",
        threshold=0.0,
    )
    assert second.triggered is False
    crossed = machine.observe(
        condition_id="other",
        session_date=date(2026, 9, 1),
        value=0.02,
        operator="cross_below",
        threshold=0.0,
    )
    crossed = machine.observe(
        condition_id="other",
        session_date=date(2026, 9, 2),
        value=-0.01,
        operator="cross_below",
        threshold=0.0,
    )
    assert crossed.triggered is True


def test_duplicate_session_does_not_increment_streak() -> None:
    machine = InvalidationStateMachine()
    first = machine.observe(
        condition_id="mom",
        session_date=date(2026, 9, 1),
        value=-30,
        operator="lt",
        threshold=-25,
    )
    duplicate = machine.observe(
        condition_id="mom",
        session_date=date(2026, 9, 1),
        value=-40,
        operator="lt",
        threshold=-25,
    )
    assert first.streak == 1
    assert duplicate.streak == 1
    nxt = machine.observe(
        condition_id="mom",
        session_date=date(2026, 9, 2),
        value=-35,
        operator="lt",
        threshold=-25,
    )
    assert nxt.streak == 2
