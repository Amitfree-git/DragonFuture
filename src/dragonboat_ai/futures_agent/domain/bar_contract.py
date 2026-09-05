from __future__ import annotations

from decimal import Decimal


class SettlementMissingError(ValueError):
    """Raised when settlement is absent; close must not be substituted."""


def validate_ohlc_settlement(
    *,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    settlement: Decimal | None,
) -> None:
    if settlement is None:
        raise SettlementMissingError("settlement is required; close must not fill settlement")
    if high < low:
        raise ValueError("high must be >= low")
    for name, value in (
        ("open", open_),
        ("high", high),
        ("low", low),
        ("close", close),
        ("settlement", settlement),
    ):
        if value.is_nan() or value.is_infinite():
            raise ValueError(f"{name} is not finite")
