from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from dragonboat_ai.futures_agent.operations.outbox import EventOutbox
from dragonboat_ai.futures_agent.operations.shadow import ShadowJournal


@dataclass(frozen=True, slots=True)
class ShadowMetrics:
    sessions: int
    gaps: int
    candidates: int
    missing_rate: float
    candidate_rate: float
    faults: dict[str, int]


def summarize_journal(journal: ShadowJournal) -> ShadowMetrics:
    sessions = len(journal.observations)
    gaps = len(journal.gaps())
    candidates = sum(1 for item in journal.observations if item.candidate_emitted)
    faults = dict(Counter(item.fault for item in journal.observations))
    return ShadowMetrics(
        sessions=sessions,
        gaps=gaps,
        candidates=candidates,
        missing_rate=(gaps / sessions) if sessions else 0.0,
        candidate_rate=(candidates / sessions) if sessions else 0.0,
        faults=faults,
    )


def operational_alerts(journal: ShadowJournal, outbox: EventOutbox | None = None) -> list[str]:
    """Named conditions a runbook can page on. Not a production alerting product."""
    alerts: list[str] = []
    metrics = summarize_journal(journal)
    if metrics.gaps:
        alerts.append("shadow_gap")
    if any(item.fault != "none" and item.candidate_emitted for item in journal.observations):
        alerts.append("candidate_emitted_during_fault")
    if outbox is not None:
        failed = [event for event in _failed_payloads(outbox)]
        if failed:
            alerts.append("outbox_publish_failed")
    return alerts


def _failed_payloads(outbox: EventOutbox) -> list[dict]:
    from sqlalchemy import select

    from dragonboat_ai.futures_agent.infrastructure.database.models import FutEventOutboxORM

    stmt = select(FutEventOutboxORM).where(FutEventOutboxORM.status == "failed")
    with outbox.session_factory() as session:
        return [row.payload_json for row in session.scalars(stmt)]
