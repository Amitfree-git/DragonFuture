from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.domain.market_data import DailyBar


@pytest.mark.point_in_time
def test_revision_is_not_visible_before_available_at(database) -> None:
    repo = database["market_repository"]
    instrument_id = repo.get_or_create_instrument(exchange="SHFE", symbol="RB")
    contract = repo.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2701",
        expiry_date=date(2027, 1, 15),
    )

    def bar(revision: int, settlement: str, available_day: int) -> DailyBar:
        price = Decimal(settlement)
        return DailyBar(
            contract_id=contract.contract_id,
            contract=contract.contract_code,
            trading_date=date(2026, 1, 2),
            open=price,
            high=price + Decimal("10"),
            low=price - Decimal("10"),
            close=price,
            settlement=price,
            previous_settlement=None,
            volume=100,
            turnover=None,
            open_interest=200,
            upper_limit=None,
            lower_limit=None,
            revision_no=revision,
            available_at=datetime(2026, 1, available_day, 8, 0, tzinfo=timezone.utc),
            source="test",
            payload_hash=f"hash-{revision}",
        )

    repo.add_daily_bar(bar(1, "3500", 3))
    repo.add_daily_bar(bar(2, "3550", 5))

    before_revision = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 1, 4, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    after_revision = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 1, 6, 8, 0, tzinfo=timezone.utc),
        limit=10,
    )
    assert before_revision[0].settlement == Decimal("3500.00000000")
    assert before_revision[0].revision_no == 1
    assert after_revision[0].settlement == Decimal("3550.00000000")
    assert after_revision[0].revision_no == 2
