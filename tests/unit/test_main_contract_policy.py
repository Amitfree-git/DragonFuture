from datetime import date
from decimal import Decimal

from dragonboat_ai.futures_agent.contracts.main_contract_policy import (
    LiquidityConfirmedMainContractPolicy,
)
from dragonboat_ai.futures_agent.domain.market_data import ContractCandidate, ContractRef


def candidate(code: str, oi: int, volume: int, trading_date: date) -> ContractCandidate:
    contract = ContractRef(
        instrument_id=1,
        contract_id=1 if code == "RB2610" else 2,
        exchange="SHFE",
        symbol="RB",
        contract_code=code,
        listed_date=None,
        last_trade_date=None,
        expiry_date=date(2027, 1, 15),
    )
    total_oi = 300_000
    total_volume = 300_000
    return ContractCandidate(
        contract=contract,
        trading_date=trading_date,
        settlement=Decimal("3500"),
        volume=volume,
        open_interest=oi,
        days_to_expiry=100,
        volume_share=volume / total_volume,
        open_interest_share=oi / total_oi,
    )


def test_unconfirmed_challenger_does_not_switch_immediately() -> None:
    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2)
    newest = [
        candidate("RB2701", 170_000, 160_000, date(2026, 9, 4)),
        candidate("RB2610", 130_000, 140_000, date(2026, 9, 4)),
    ]
    previous = [
        candidate("RB2610", 180_000, 160_000, date(2026, 9, 3)),
        candidate("RB2701", 120_000, 140_000, date(2026, 9, 3)),
    ]
    result = policy.select([newest, previous])
    assert result.selected.contract.contract_code == "RB2610"
    assert result.challenger_confirmed is False


def test_confirmed_challenger_switches() -> None:
    policy = LiquidityConfirmedMainContractPolicy(confirmation_days=2)
    history = [
        [
            candidate("RB2701", 180_000, 160_000, date(2026, 9, 4)),
            candidate("RB2610", 120_000, 140_000, date(2026, 9, 4)),
        ],
        [
            candidate("RB2701", 175_000, 155_000, date(2026, 9, 3)),
            candidate("RB2610", 125_000, 145_000, date(2026, 9, 3)),
        ],
    ]
    result = policy.select(history)
    assert result.selected.contract.contract_code == "RB2701"
    assert result.challenger_confirmed is True
