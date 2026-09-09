from __future__ import annotations

from decimal import Decimal


class SettlementMissingError(ValueError):
    """Raised when settlement is absent; close must not be substituted."""


def validate_ohlc_settlement(
    *,
    open_: Decimal | None,
    high: Decimal | None,
    low: Decimal | None,
    close: Decimal | None,
    settlement: Decimal | None,
) -> None:
    if settlement is None:
        raise SettlementMissingError("settlement is required; close must not fill settlement")
    if high is not None and low is not None and high < low:
        raise ValueError("high must be >= low")
    for name, value in (
        ("open", open_),
        ("high", high),
        ("low", low),
        ("close", close),
        ("settlement", settlement),
    ):
        if value is not None and (value.is_nan() or value.is_infinite()):
            raise ValueError(f"{name} is not finite")
