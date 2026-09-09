from datetime import date, datetime, timedelta

from dragonboat_ai.futures_agent.operations.watermark import (
    SHANGHAI,
    WatermarkStatus,
    evaluate_watermark,
)

SESSION = date(2026, 9, 4)


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 4, hour, minute, tzinfo=SHANGHAI)


def _settlement(hour: int = 15, minute: int = 0) -> datetime:
    return datetime(2026, 9, 4, hour, minute, tzinfo=SHANGHAI)


def test_shfe_watermark_is_session_close_not_1630() -> None:
    too_early = evaluate_watermark(
        exchange="SHFE",
        session_date=SESSION,
        now=_at(14, 59),
        settlement_available_at=_settlement(),
    )
    just_closed = evaluate_watermark(
        exchange="SHFE",
        session_date=SESSION,
        now=_at(15, 1),
        settlement_available_at=_settlement(),
    )
    assert too_early.status is WatermarkStatus.TOO_EARLY
    assert too_early.run is False
    assert just_closed.status is WatermarkStatus.READY
    assert just_closed.run is True


def test_cffex_stays_closed_after_shfe_but_before_1515() -> None:
    decision = evaluate_watermark(
        exchange="CFFEX",
        session_date=SESSION,
        now=_at(15, 10),
        settlement_available_at=_settlement(15, 15),
    )
    assert decision.status is WatermarkStatus.TOO_EARLY
    assert decision.run is False


def test_missing_settlement_is_a_recorded_gap() -> None:
    decision = evaluate_watermark(
        exchange="SHFE",
        session_date=SESSION,
        now=_at(16, 0),
        settlement_available_at=None,
    )
    assert decision.status is WatermarkStatus.MISSING
    assert decision.run is False
    assert decision.degrade is True


def test_stale_settlement_from_earlier_session() -> None:
    decision = evaluate_watermark(
        exchange="SHFE",
        session_date=SESSION,
        now=_at(16, 0),
        settlement_available_at=_settlement() - timedelta(days=2),
    )
    assert decision.status is WatermarkStatus.STALE
    assert decision.run is False


def test_future_settlement_timestamp_is_lookahead() -> None:
    decision = evaluate_watermark(
        exchange="SHFE",
        session_date=SESSION,
        now=_at(15, 1),
        settlement_available_at=_settlement(16, 0),
    )
    assert decision.status is WatermarkStatus.LOOKAHEAD_BLOCKED
    assert decision.run is False
