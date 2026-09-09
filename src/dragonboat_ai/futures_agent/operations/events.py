from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis

EVENT_TYPE = "futures.market_analysis.published"
SCHEMA_VERSION = "1.0.0"
BLOCKING_ACTIONS = {"no_trade", "insufficient_data"}


def build_published_event(analysis: FuturesMarketAnalysis) -> dict[str, Any]:
    core = analysis.model_dump(mode="json", exclude={"narrative"})
    return {
        "event_id": str(uuid4()),
        "event_type": EVENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "analysis_id": analysis.analysis_id,
        "core_result_hash": analysis.core_result_hash,
        "as_of": analysis.request.as_of.astimezone(timezone.utc).isoformat(),
        "instrument": {
            "exchange": analysis.request.exchange,
            "symbol": analysis.request.symbol,
        },
        "contract": analysis.selected_contract,
        "horizon": analysis.request.horizon.value,
        "action": analysis.opportunity.action.value,
        "hard_gate": analysis.risk.hard_gate_triggered,
        "data_mode": analysis.data_mode,
        "production_ready": analysis.production_ready,
        "payload": core,
    }


def consumer_intent(event: dict[str, Any]) -> str:
    """Downstream must read action and hard_gate, never infer a weak order from no_trade."""
    action = str(event.get("action") or "")
    hard_gate = bool(event.get("hard_gate"))
    if hard_gate or action in BLOCKING_ACTIONS:
        return "blocked"
    if action == "long_candidate":
        return "long_candidate"
    if action == "short_candidate":
        return "short_candidate"
    return "observe"


class DedupingConsumer:
    def __init__(self) -> None:
        self._seen: set[str] = set()
        self.processed: list[str] = []

    def consume(self, event: dict[str, Any]) -> str:
        event_id = str(event["event_id"])
        if event_id in self._seen:
            return "duplicate"
        self._seen.add(event_id)
        intent = consumer_intent(event)
        self.processed.append(intent)
        return intent
