import pytest

from dragonboat_ai.futures_agent.domain.enums import OpportunityAction
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FuturesMarketAnalysis
from dragonboat_ai.futures_agent.operations.events import DedupingConsumer, consumer_intent
from dragonboat_ai.futures_agent.operations.outbox import EventOutbox
from tests.support import seed_reference_market


def test_no_trade_is_blocked_not_a_weak_order() -> None:
    event = {
        "event_id": "e1",
        "action": OpportunityAction.NO_TRADE.value,
        "hard_gate": False,
    }
    assert consumer_intent(event) == "blocked"
    hard = {"event_id": "e2", "action": "wait_for_pullback", "hard_gate": True}
    assert consumer_intent(hard) == "blocked"
    long_event = {"event_id": "e3", "action": "long_candidate", "hard_gate": False}
    assert consumer_intent(long_event) == "long_candidate"


@pytest.mark.integration
def test_outbox_survives_publish_failure_and_consumer_dedupes(database) -> None:
    from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
    from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder

    market = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market),
        analysis_repository=analysis_repo,
    )
    analysis = analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            include_narrative=False,
        )
    )
    assert isinstance(analysis, FuturesMarketAnalysis)

    outbox = EventOutbox(database["session_factory"])
    pending = outbox.pending()
    assert len(pending) == 1
    event = pending[0]
    assert event["event_type"] == "futures.market_analysis.published"
    assert event["analysis_id"] == analysis.analysis_id

    outbox.mark_failed(event["event_id"], "broker unavailable")
    assert outbox.pending() == []
    retried = outbox.retry_failed()
    assert len(retried) == 1
    outbox.mark_published(event["event_id"])
    assert outbox.pending() == []

    consumer = DedupingConsumer()
    assert consumer.consume(event) in {"blocked", "long_candidate", "short_candidate", "observe"}
    assert consumer.consume(event) == "duplicate"
