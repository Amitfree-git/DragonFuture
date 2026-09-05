from decimal import Decimal

import pytest

from dragonboat_ai.futures_agent.domain.bar_contract import SettlementMissingError, validate_ohlc_settlement


def test_close_does_not_fill_settlement() -> None:
    with pytest.raises(SettlementMissingError):
        validate_ohlc_settlement(
            open_=Decimal("3500"),
            high=Decimal("3510"),
            low=Decimal("3490"),
            close=Decimal("3505"),
            settlement=None,
        )
