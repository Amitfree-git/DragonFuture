from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time as dtime
from enum import Enum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis
from dragonboat_ai.futures_agent.infrastructure.database.models import FutShadowRunORM
from dragonboat_ai.futures_agent.operations.watermark import (
    SHANGHAI,
    WatermarkDecision,
    evaluate_watermark,
)


class ShadowFault(str, Enum):
    NONE = "none"
    NETWORK = "network"
    MISSING_FIELD = "missing_field"
    DUPLICATE_BATCH = "duplicate_batch"
    STALE = "stale"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    session_date: date
    exchange: str
    symbol: str
    horizon: str
    watermark_status: str
    input_data_hash: str | None
    core_result_hash: str | None
    opportunity_action: str | None
    hard_gate: bool
    blocking_reasons: tuple[str, ...]
    gap: bool
    candidate_emitted: bool
    fault: str
    review_notes: str | None = None


@dataclass
class ShadowJournal:
    observations: list[ShadowObservation] = field(default_factory=list)

    def record(self, observation: ShadowObservation) -> None:
        self.observations.append(observation)

    def gaps(self) -> list[ShadowObservation]:
        return [item for item in self.observations if item.gap]


class SqlShadowStore:
    """Persist shadow observations so gaps stay queryable. Not a live trading blotter."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def save(self, observation: ShadowObservation) -> None:
        with self.session_factory.begin() as session:
            session.add(
                FutShadowRunORM(
                    run_id=str(uuid4()),
                    exchange=observation.exchange,
                    symbol=observation.symbol,
                    session_date=observation.session_date,
                    horizon=observation.horizon,
                    watermark_status=observation.watermark_status,
                    input_data_hash=observation.input_data_hash,
                    core_result_hash=observation.core_result_hash,
                    opportunity_action=observation.opportunity_action,
                    hard_gate=observation.hard_gate,
                    gap=observation.gap,
                    candidate_emitted=observation.candidate_emitted,
                    blocking_reasons=list(observation.blocking_reasons),
                    review_notes=observation.review_notes,
                )
            )


class ShadowRunner:
    """Read-only daily shadow loop. Never places orders."""

    def __init__(
        self,
        journal: ShadowJournal | None = None,
        store: SqlShadowStore | None = None,
    ) -> None:
        self.journal = journal or ShadowJournal()
        self.store = store

    def run_session(
        self,
        *,
        exchange: str,
        symbol: str,
        session_date: date,
        now: datetime,
        settlement_available_at: datetime | None,
        analyze,
        fault: ShadowFault = ShadowFault.NONE,
        horizon: str = "swing",
    ) -> ShadowObservation:
        if fault is ShadowFault.STALE:
            settlement_available_at = datetime.combine(
                session_date - timedelta(days=3),
                dtime(15, 0),
                tzinfo=SHANGHAI,
            )
        decision = evaluate_watermark(
            exchange=exchange,
            session_date=session_date,
            now=now,
            settlement_available_at=settlement_available_at,
        )
        if fault is ShadowFault.NETWORK:
            return self._record(
                self._blocked(
                    session_date, exchange, symbol, horizon, decision, fault, "network_unavailable"
                )
            )
        if not decision.run:
            return self._record(
                self._blocked(
                    session_date, exchange, symbol, horizon, decision, fault, decision.reason
                )
            )
        if fault is ShadowFault.MISSING_FIELD:
            return self._record(
                self._blocked(
                    session_date, exchange, symbol, horizon, decision, fault, "missing_critical_field"
                )
            )
        try:
            analysis: FuturesMarketAnalysis = analyze()
            if fault is ShadowFault.DUPLICATE_BATCH:
                analyze()
        except TimeoutError:
            observation = ShadowObservation(
                session_date=session_date,
                exchange=exchange,
                symbol=symbol,
                horizon=horizon,
                watermark_status=decision.status.value,
                input_data_hash=None,
                core_result_hash=None,
                opportunity_action=None,
                hard_gate=True,
                blocking_reasons=("model_timeout",),
                gap=True,
                candidate_emitted=False,
                fault=ShadowFault.TIMEOUT.value,
            )
            self._record(observation)
            raise
        action = analysis.opportunity.action.value
        candidate = action in {"long_candidate", "short_candidate"} and not analysis.risk.hard_gate_triggered
        return self._record(
            ShadowObservation(
                session_date=session_date,
                exchange=exchange,
                symbol=symbol,
                horizon=horizon,
                watermark_status=decision.status.value,
                input_data_hash=analysis.input_data_hash,
                core_result_hash=analysis.core_result_hash,
                opportunity_action=action,
                hard_gate=analysis.risk.hard_gate_triggered,
                blocking_reasons=tuple(analysis.opportunity.hard_gate_reasons),
                gap=False,
                candidate_emitted=candidate,
                fault=fault.value,
            )
        )

    def _record(self, observation: ShadowObservation) -> ShadowObservation:
        self.journal.record(observation)
        if self.store is not None:
            self.store.save(observation)
        return observation

    @staticmethod
    def _blocked(
        session_date: date,
        exchange: str,
        symbol: str,
        horizon: str,
        decision: WatermarkDecision,
        fault: ShadowFault,
        reason: str,
    ) -> ShadowObservation:
        return ShadowObservation(
            session_date=session_date,
            exchange=exchange,
            symbol=symbol,
            horizon=horizon,
            watermark_status=decision.status.value,
            input_data_hash=None,
            core_result_hash=None,
            opportunity_action=None,
            hard_gate=True,
            blocking_reasons=(reason,),
            gap=True,
            candidate_emitted=False,
            fault=fault.value,
        )
