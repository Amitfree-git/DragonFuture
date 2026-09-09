from datetime import date, time
from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.contracts.calendar import ExchangeCalendar, SessionHours
from dragonboat_ai.futures_agent.contracts.continuous_series import (
    BackwardAdditiveContinuousSeriesBuilder,
    RawContinuousPoint,
    RollGap,
)
from dragonboat_ai.futures_agent.contracts.main_contract_policy import (
    LiquidityConfirmedMainContractPolicy,
)
from dragonboat_ai.futures_agent.contracts.main_contract_state import (
    MappingAction,
    MainContractStateMachine,
)
from dragonboat_ai.futures_agent.contracts.research_returns import same_contract_return_index
from dragonboat_ai.futures_agent.contracts.series_snapshot import ChartSeriesStore
from dragonboat_ai.futures_agent.domain.market_data import ContractCandidate, ContractRef


def _ref(code: str, contract_id: int, last_trade: date | None = None) -> ContractRef:
    return ContractRef(
        instrument_id=1,
        contract_id=contract_id,
        exchange="SHFE",
        symbol="RB",
        contract_code=code,
        listed_date=None,
        last_trade_date=last_trade,
        expiry_date=last_trade or date(2027, 1, 15),
    )


def _cand(
    code: str,
    oi: int,
    volume: int,
    trading_date: date,
    *,
    contract_id: int | None = None,
    dte: int = 100,
) -> ContractCandidate:
    cid = contract_id if contract_id is not None else (1 if code == "RB2610" else 2)
    total = max(oi + volume, 1)
    return ContractCandidate(
        contract=_ref(code, cid),
        trading_date=trading_date,
        settlement=Decimal("3500"),
        volume=volume,
        open_interest=oi,
        days_to_expiry=dte,
        volume_share=volume / total,
        open_interest_share=oi / total,
    )


def test_tied_candidates_are_deterministic() -> None:
    policy = LiquidityConfirmedMainContractPolicy()
    day = date(2026, 9, 1)
    tied = [
        _cand("RB2705", 100_000, 100_000, day, contract_id=3, dte=200),
        _cand("RB2701", 100_000, 100_000, day, contract_id=2, dte=200),
    ]
    first = policy.rank(tied)
    second = policy.rank(list(reversed(tied)))
    assert first.contract.contract_code == second.contract.contract_code == "RB2701"


def test_confirmation_breaks_on_missing_session() -> None:
    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2)
    machine = MainContractStateMachine(policy)
    d1, d2, d3, d4 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)
    sessions = [
        (d1, [_cand("RB2610", 200_000, 150_000, d1), _cand("RB2701", 100_000, 80_000, d1)]),
        (d2, [_cand("RB2701", 190_000, 160_000, d2), _cand("RB2610", 180_000, 140_000, d2)]),
        (d3, None),
        (d4, [_cand("RB2701", 200_000, 170_000, d4), _cand("RB2610", 120_000, 90_000, d4)]),
    ]
    records = machine.replay(sessions)
    by_date = {item.session_date: item for item in records}
    assert by_date[d4].effective_contract == "RB2610"
    assert by_date[d4].action is MappingAction.KEEP
    assert by_date[d4].challenger_streak == 1


def test_roll_not_effective_on_decision_day() -> None:
    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2)
    machine = MainContractStateMachine(policy)
    d1, d2, d3, d4 = date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)
    sessions = [
        (d1, [_cand("RB2610", 200_000, 150_000, d1), _cand("RB2701", 100_000, 80_000, d1)]),
        (d2, [_cand("RB2701", 190_000, 160_000, d2), _cand("RB2610", 180_000, 140_000, d2)]),
        (d3, [_cand("RB2701", 200_000, 170_000, d3), _cand("RB2610", 120_000, 90_000, d3)]),
        (d4, [_cand("RB2701", 210_000, 180_000, d4), _cand("RB2610", 100_000, 70_000, d4)]),
    ]
    records = machine.replay(sessions)
    by_date = {item.session_date: item for item in records}
    assert by_date[d3].effective_contract == "RB2610"
    assert by_date[d4].effective_contract == "RB2701"
    assert by_date[d3].action is MappingAction.CONFIRMED_ROLL
    assert by_date[d3].effective_session == d4


def test_next_session_respects_holiday() -> None:
    calendar = ExchangeCalendar(
        exchange="SHFE",
        version="test",
        timezone_name="Asia/Shanghai",
        sessions=SessionHours(
            night_open=time.fromisoformat("21:00"),
            night_close=time.fromisoformat("23:00"),
            day_open=time.fromisoformat("09:00"),
            day_close=time.fromisoformat("15:00"),
        ),
        holidays=frozenset({date(2026, 9, 7)}),
    )
    friday = date(2026, 9, 4)
    assert calendar.next_trading_day(friday) == date(2026, 9, 8)

    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2)
    machine = MainContractStateMachine(policy, calendar=calendar)
    d1, d2, d3 = date(2026, 9, 2), date(2026, 9, 3), date(2026, 9, 4)
    sessions = [
        (d1, [_cand("RB2610", 200_000, 150_000, d1)]),
        (d2, [_cand("RB2701", 190_000, 160_000, d2), _cand("RB2610", 180_000, 140_000, d2)]),
        (d3, [_cand("RB2701", 200_000, 170_000, d3), _cand("RB2610", 120_000, 90_000, d3)]),
    ]
    records = machine.replay(sessions)
    assert records[-1].action is MappingAction.CONFIRMED_ROLL
    assert records[-1].effective_session == date(2026, 9, 8)


def test_ineligible_incumbent_never_silently_traded() -> None:
    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2, exclude_days_to_expiry_below=10)
    machine = MainContractStateMachine(policy)
    d1, d2 = date(2026, 9, 1), date(2026, 9, 2)
    sessions = [
        (d1, [_cand("RB2610", 200_000, 150_000, d1, dte=100)]),
        (d2, [_cand("RB2610", 200_000, 150_000, d2, dte=5), _cand("RB2701", 80_000, 70_000, d2, dte=100)]),
    ]
    records = machine.replay(sessions)
    assert records[-1].effective_contract != "RB2610"
    assert records[-1].action in {MappingAction.EMERGENCY_ROLL, MappingAction.BLOCKED}
    if records[-1].action is MappingAction.EMERGENCY_ROLL:
        assert records[-1].effective_contract == "RB2701"


def test_roll_gap_not_counted_as_market_return() -> None:
    points = [
        RawContinuousPoint(date(2026, 8, 31), "RB2610", Decimal("100")),
        RawContinuousPoint(date(2026, 9, 1), "RB2701", Decimal("110")),
    ]
    gaps = [
        RollGap(
            effective_date=date(2026, 9, 1),
            from_contract="RB2610",
            to_contract="RB2701",
            from_settlement=Decimal("100"),
            to_settlement=Decimal("110"),
        )
    ]
    index = same_contract_return_index(points, gaps, previous_settlements={(date(2026, 9, 1), "RB2701"): Decimal("110")})
    assert index[0].index_value == Decimal("100")
    assert index[-1].index_value == Decimal("100")
    chart = BackwardAdditiveContinuousSeriesBuilder().build(points, gaps)
    naive_return = points[-1].settlement / points[0].settlement
    research_return = index[-1].index_value / index[0].index_value
    assert research_return == Decimal("1")
    assert naive_return != research_return
    assert chart[0].adjusted_settlement == Decimal("110")


def test_chart_rebase_does_not_change_return_index() -> None:
    points = [
        RawContinuousPoint(date(2026, 8, 31), "RB2610", Decimal("100")),
        RawContinuousPoint(date(2026, 9, 1), "RB2610", Decimal("101")),
    ]
    base = same_contract_return_index(points, [])
    rebased = [
        RawContinuousPoint(item.trading_date, item.source_contract, item.settlement * Decimal("2"))
        for item in points
    ]
    other = same_contract_return_index(rebased, [])
    assert [item.index_value for item in base] == [item.index_value for item in other]


def test_backadjustment_vintage_is_immutable() -> None:
    store = ChartSeriesStore()
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
    first = store.build_and_save("snap-1", points, gaps)
    mutated = list(points) + [RawContinuousPoint(date(2026, 9, 2), "RB2701", Decimal("3910"))]
    store.build_and_save("snap-2", mutated, gaps)
    loaded = store.get("snap-1")
    assert loaded is not None
    assert loaded.points == first.points
    with pytest.raises(ValueError):
        store.build_and_save("snap-1", mutated, gaps)


def test_research_roll_requires_incoming_prior_settlement():
    points = [RawContinuousPoint(date(2026,9,1),'A',Decimal(100)), RawContinuousPoint(date(2026,9,2),'B',Decimal(220))]
    assert same_contract_return_index(points, [])[1].index_value is None
    assert same_contract_return_index(points, [], previous_settlements={(date(2026,9,2),'B'): Decimal(200)})[1].index_value == Decimal(110)


def test_research_nonpositive_price_breaks_index():
    points = [RawContinuousPoint(date(2026,9,1),'A',Decimal(100)), RawContinuousPoint(date(2026,9,2),'A',Decimal(-1))]
    assert same_contract_return_index(points, [])[1].index_value is None


def test_blocked_session_resets_internal_challenger_streak():
    days=[date(2026,9,1),date(2026,9,2),date(2026,9,3),date(2026,9,4),date(2026,9,7)]
    sessions=[]
    for i,d in enumerate(days):
        if i==2:
            sessions.append((d,[]))
        else:
            sessions.append((d,[_cand('RB2610',200 if i in (0,3) else 100,200 if i in (0,3) else 100,d),_cand('RB2701',100 if i in (0,3) else 200,100 if i in (0,3) else 200,d)]))
    records=MainContractStateMachine(LiquidityConfirmedMainContractPolicy(confirmation_days=2)).replay(sessions)
    assert records[-1].action is MappingAction.KEEP
    assert records[-1].challenger_streak == 1
