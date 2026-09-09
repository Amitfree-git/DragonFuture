from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from dragonboat_ai.futures_agent.contracts.calendar import ExchangeCalendar
from dragonboat_ai.futures_agent.contracts.main_contract_policy import LiquidityConfirmedMainContractPolicy
from dragonboat_ai.futures_agent.domain.market_data import ContractCandidate


class MappingAction(str, Enum):
    KEEP = "keep"
    CONFIRMED_ROLL = "confirmed_roll"
    EMERGENCY_ROLL = "emergency_roll"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MappingRecord:
    session_date: date
    effective_contract: str | None
    effective_session: date | None
    action: MappingAction
    challenger_streak: int
    decision_contract: str | None


class MainContractStateMachine:
    def __init__(
        self,
        policy: LiquidityConfirmedMainContractPolicy,
        calendar: ExchangeCalendar | None = None,
    ) -> None:
        self.policy = policy
        self.calendar = calendar or ExchangeCalendar.weekday_sessions(
            exchange="SHFE",
            version="weekday_v1",
            night_open="21:00",
            night_close="23:00",
            day_open="09:00",
            day_close="15:00",
        )

    def replay(
        self,
        sessions: list[tuple[date, list[ContractCandidate] | None]],
    ) -> list[MappingRecord]:
        effective: str | None = None
        pending: str | None = None
        pending_from: date | None = None
        challenger: str | None = None
        streak = 0
        records: list[MappingRecord] = []
        expanded: list[tuple[date, list[ContractCandidate] | None]] = []
        for session_date, candidates in sorted(sessions, key=lambda item: item[0]):
            if expanded:
                missing = self.calendar.next_trading_day(expanded[-1][0])
                while missing < session_date:
                    expanded.append((missing, None))
                    missing = self.calendar.next_trading_day(missing)
            expanded.append((session_date, candidates))
        for session_date, candidates in expanded:
            if pending is not None and pending_from is not None and session_date >= pending_from:
                effective = pending
                pending = None
                pending_from = None
                challenger = None
                streak = 0

            next_session = self.calendar.next_trading_day(session_date)
            if candidates is None:
                streak = 0
                challenger = None
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=None,
                        action=MappingAction.KEEP,
                        challenger_streak=0,
                        decision_contract=effective,
                    )
                )
                continue

            eligible = self.policy._eligible(candidates)
            ranked = self.policy.rank(eligible) if eligible else None
            incumbent_ok = any(
                item.contract.contract_code == effective for item in eligible
            ) if effective is not None else False

            if effective is None:
                challenger = None
                streak = 0
                if ranked is None:
                    challenger = None
                    streak = 0
                    records.append(
                        MappingRecord(
                            session_date=session_date,
                            effective_contract=None,
                            effective_session=None,
                            action=MappingAction.BLOCKED,
                            challenger_streak=0,
                            decision_contract=None,
                        )
                    )
                    continue
                effective = ranked.contract.contract_code
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=session_date,
                        action=MappingAction.KEEP,
                        challenger_streak=0,
                        decision_contract=effective,
                    )
                )
                continue

            if not incumbent_ok:
                if ranked is None:
                    challenger = None
                    streak = 0
                    records.append(
                        MappingRecord(
                            session_date=session_date,
                            effective_contract=None,
                            effective_session=None,
                            action=MappingAction.BLOCKED,
                            challenger_streak=0,
                            decision_contract=None,
                        )
                    )
                    effective = None
                    continue
                effective = ranked.contract.contract_code
                streak = 0
                challenger = None
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=session_date,
                        action=MappingAction.EMERGENCY_ROLL,
                        challenger_streak=0,
                        decision_contract=effective,
                    )
                )
                continue

            top = ranked.contract.contract_code if ranked is not None else effective
            if top == effective:
                streak = 0
                challenger = None
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=None,
                        action=MappingAction.KEEP,
                        challenger_streak=0,
                        decision_contract=effective,
                    )
                )
                continue

            if challenger == top:
                streak += 1
            else:
                challenger = top
                streak = 1
            if streak >= self.policy.confirmation_days:
                pending = top
                pending_from = next_session
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=next_session,
                        action=MappingAction.CONFIRMED_ROLL,
                        challenger_streak=streak,
                        decision_contract=top,
                    )
                )
            else:
                records.append(
                    MappingRecord(
                        session_date=session_date,
                        effective_contract=effective,
                        effective_session=None,
                        action=MappingAction.KEEP,
                        challenger_streak=streak,
                        decision_contract=effective,
                    )
                )
        return records
