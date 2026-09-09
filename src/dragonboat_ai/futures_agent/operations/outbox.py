from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dragonboat_ai.futures_agent.infrastructure.database.models import FutEventOutboxORM


class EventOutbox:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def enqueue(self, session: Session, event: dict[str, Any]) -> None:
        session.add(
            FutEventOutboxORM(
                event_id=event["event_id"],
                event_type=event["event_type"],
                analysis_id=event["analysis_id"],
                payload_json=event,
                status="pending",
                available_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )

    def pending(self) -> list[dict[str, Any]]:
        stmt = select(FutEventOutboxORM).where(FutEventOutboxORM.status == "pending")
        with self.session_factory() as session:
            return [row.payload_json for row in session.scalars(stmt)]

    def mark_published(self, event_id: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(FutEventOutboxORM, event_id)
            if row is None:
                return
            row.status = "published"
            row.published_at = datetime.now(timezone.utc).replace(tzinfo=None)

    def mark_failed(self, event_id: str, error: str) -> None:
        with self.session_factory.begin() as session:
            row = session.get(FutEventOutboxORM, event_id)
            if row is None:
                return
            row.status = "failed"
            row.last_error = error[:500]
            row.attempt_count = (row.attempt_count or 0) + 1

    def retry_failed(self) -> list[dict[str, Any]]:
        with self.session_factory.begin() as session:
            rows = list(
                session.scalars(select(FutEventOutboxORM).where(FutEventOutboxORM.status == "failed"))
            )
            events = []
            for row in rows:
                row.status = "pending"
                events.append(row.payload_json)
            return events
