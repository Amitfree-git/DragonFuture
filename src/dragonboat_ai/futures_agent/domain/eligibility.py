from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ProductRule:
    exchange: str
    symbol: str
    version: str
    last_trade_date: date
    expiry_date: date
    account_eligible: bool
    tradable_until_override: date | None = None


def production_candidate_allowed(rule: ProductRule | None) -> bool:
    if rule is None:
        return False
    return rule.account_eligible


def tradable_until(rule: ProductRule) -> date:
    if rule.tradable_until_override is not None:
        return rule.tradable_until_override
    return rule.last_trade_date
