from datetime import date

from dragonboat_ai.futures_agent.domain.eligibility import (
    ProductRule,
    production_candidate_allowed,
    tradable_until,
)


def test_missing_product_rules_blocks_production_candidate() -> None:
    assert production_candidate_allowed(None) is False


def test_tradable_until_uses_last_trade_not_uniform_seven_days() -> None:
    rule = ProductRule(
        exchange="SHFE",
        symbol="RB",
        version="rb_delivery_v1",
        last_trade_date=date(2026, 10, 15),
        expiry_date=date(2026, 10, 20),
        account_eligible=True,
    )
    until = tradable_until(rule)
    assert until == date(2026, 10, 15)
    assert (until - date(2026, 10, 8)).days != 7 or until == date(2026, 10, 15)
    assert until != date(2026, 10, 20) - __import__("datetime").timedelta(days=7)


def test_ineligible_account_cannot_form_production_candidate() -> None:
    rule = ProductRule(
        exchange="SHFE",
        symbol="RB",
        version="rb_delivery_v1",
        last_trade_date=date(2026, 10, 15),
        expiry_date=date(2026, 10, 20),
        account_eligible=False,
    )
    assert production_candidate_allowed(rule) is False
