from datetime import date, datetime, timezone

import pytest

from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest

from tests.support import seed_reference_market


@pytest.mark.integration
def test_context_uses_effective_mapping_not_curve_winner(database) -> None:
    market_repo = database["market_repository"]
    fixture = seed_reference_market(market_repo)
    as_of = fixture["as_of"]
    builder = SqlAlchemyMarketContextBuilder(market_repo)
    auto = builder.build(AnalysisRequest(symbol="RB", exchange="SHFE", as_of=as_of))
    assert auto.selected_contract == "RB2701"

    market_repo.save_contract_mapping(
        mapping_id="map-rb2610",
        instrument_id=fixture["instrument_id"],
        to_contract_id=fixture["rb2610"].contract_id,
        decision_date=date(2026, 9, 3),
        effective_session=as_of.date(),
        action="keep",
        available_at=datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc),
    )
    mapped = builder.build(AnalysisRequest(symbol="RB", exchange="SHFE", as_of=as_of))
    assert mapped.selected_contract == "RB2610"
    assert mapped.contract_selection_reason == "effective_session_mapping"
    assert mapped.mapping_effective_session == as_of.date()


@pytest.mark.integration
def test_mapping_not_effective_on_decision_day(database) -> None:
    market_repo = database["market_repository"]
    fixture = seed_reference_market(market_repo)
    as_of = fixture["as_of"]
    builder = SqlAlchemyMarketContextBuilder(market_repo)
    market_repo.save_contract_mapping(
        mapping_id="map-future",
        instrument_id=fixture["instrument_id"],
        to_contract_id=fixture["rb2610"].contract_id,
        decision_date=as_of.date(),
        effective_session=date(2026, 9, 7),
        action="confirmed_roll",
        available_at=as_of,
    )
    context = builder.build(AnalysisRequest(symbol="RB", exchange="SHFE", as_of=as_of))
    assert context.selected_contract == "RB2701"
    assert context.contract_selection_reason != "effective_session_mapping"
