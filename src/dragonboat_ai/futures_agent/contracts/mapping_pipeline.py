from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from dragonboat_ai.futures_agent.contracts.calendar import ExchangeCalendar
from dragonboat_ai.futures_agent.contracts.continuous_series import (
    BackwardAdditiveContinuousSeriesBuilder,
    RawContinuousPoint,
    RollGap,
)
from dragonboat_ai.futures_agent.contracts.research_returns import same_contract_return_index
from dragonboat_ai.futures_agent.contracts.main_contract_policy import LiquidityConfirmedMainContractPolicy
from dragonboat_ai.futures_agent.contracts.main_contract_state import MappingAction, MainContractStateMachine
from dragonboat_ai.futures_agent.domain.market_data import ContinuousBar, ContractCandidate
from dragonboat_ai.futures_agent.infrastructure.database.calendar_store import SqlAlchemyCalendarStore
from dragonboat_ai.futures_agent.infrastructure.database.repositories import SqlAlchemyMarketDataRepository
from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import (
    parse_trade_date,
    settlement_available_at,
)
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig


@dataclass(frozen=True, slots=True)
class MappingBuildReport:
    instrument_id: int
    sessions: int
    mappings: int
    rolls: int
    continuous_bars: int
    blocked_sessions: int


def ingest_trade_calendar(
    store: SqlAlchemyCalendarStore,
    rows: list[dict],
    *,
    version: str = "tushare_trade_cal_v1",
) -> int:
    written = 0
    for row in rows:
        trading_date = parse_trade_date(str(row["cal_date"]))
        is_open = str(row.get("is_open")) in {"1", "1.0", "true", "True"}
        available_at = settlement_available_at(trading_date)
        store.add_day(
            exchange=str(row.get("exchange") or "SHFE"),
            version=version,
            trading_date=trading_date,
            is_trading_day=is_open,
            available_at=available_at,
            revision_no=1,
            published_at=available_at,
            source="tushare",
        )
        written += 1
    return written


def calendar_from_trade_cal(rows: list[dict], *, exchange: str) -> ExchangeCalendar:
    holidays = frozenset(
        parse_trade_date(str(row["cal_date"]))
        for row in rows
        if str(row.get("is_open")) not in {"1", "1.0", "true", "True"}
    )
    return ExchangeCalendar.weekday_sessions(
        exchange=exchange,
        version="tushare_trade_cal_v1",
        night_open="21:00",
        night_close="23:00",
        day_open="09:00",
        day_close="15:00",
        holidays=holidays,
    )


def build_mapping_and_continuous(
    repository: SqlAlchemyMarketDataRepository,
    *,
    symbol: str,
    exchange: str,
    as_of: datetime,
    config: ScoringConfig | None = None,
    calendar: ExchangeCalendar | None = None,
) -> MappingBuildReport:
    """Persist complete immutable vintages at each input knowledge time.

    Full and incremental builds use the same prefixes, including late revisions.
    Readers select one complete vintage; backward adjustments are never mixed
    across runs or marked as known on a historical point's trading date.
    """
    config = config or ScoringConfig.default()
    instrument = repository.resolve_instrument(symbol=symbol, exchange=exchange)
    main = config.main_contract
    policy = LiquidityConfirmedMainContractPolicy(
        exclude_days_to_expiry_below=int(main["exclude_days_to_expiry_below"]),
        confirmation_days=int(main["confirmation_days"]),
        minimum_volume_share=main["minimum_volume_share"],
        minimum_oi_share=main["minimum_oi_share"],
    )
    machine = MainContractStateMachine(policy, calendar=calendar)
    report = MappingBuildReport(instrument.instrument_id, 0, 0, 0, 0, 0)
    for cutoff in repository.curve_visibility_times(instrument_id=instrument.instrument_id, as_of=as_of):
        curves = repository.load_curve_snapshots(instrument_id=instrument.instrument_id, as_of=cutoff, limit=100000)
        sessions = [(curve.trading_date, repository.candidates_from_curve(curve)) for curve in curves]
        records = machine.replay(sessions)
        candidates = {day: {c.contract.contract_code: c for c in items} for day, items in sessions}
        by_date = {curve.trading_date: curve for curve in curves}
        source_ids = {c.contract.contract_code: c.contract.contract_id for _, items in sessions for c in items}
        raw_points: list[RawContinuousPoint] = []
        gaps: list[RollGap] = []
        denominators: dict[tuple[date, str], Decimal] = {}
        mapping_payload = []
        previous = None
        for record in records:
            code = record.decision_contract if record.action is MappingAction.CONFIRMED_ROLL else record.effective_contract
            mapping_payload.append({
                "decision_date": record.session_date.isoformat(),
                "effective_session": (record.effective_session or record.session_date).isoformat(),
                "to_contract_id": source_ids.get(code),
                "action": record.action.value,
                "policy_version": "main_contract_v1",
            })
            current = candidates.get(record.session_date, {}).get(record.effective_contract)
            if current is None:
                continue
            if previous is not None:
                previous_day = previous.trading_date
                prior = candidates.get(previous_day, {}).get(record.effective_contract)
                if prior is not None:
                    denominators[(record.session_date, record.effective_contract)] = prior.settlement
                if previous.source_contract != record.effective_contract:
                    outgoing = candidates.get(record.session_date, {}).get(previous.source_contract)
                    if outgoing is not None:
                        gaps.append(RollGap(record.session_date, previous.source_contract, record.effective_contract,
                                            outgoing.settlement, current.settlement))
            previous = RawContinuousPoint(record.session_date, record.effective_contract, current.settlement)
            raw_points.append(previous)
        adjusted = BackwardAdditiveContinuousSeriesBuilder().build(raw_points, gaps)
        index = same_contract_return_index(raw_points, gaps, previous_settlements=denominators, calendar=machine.calendar)
        payload = {
            "version": "causal_series_v2",
            "symbol": symbol,
            "calendar": {"version": machine.calendar.version, "holidays": sorted(d.isoformat() for d in machine.calendar.holidays)},
            "policy": main,
            "inputs": [(c.snapshot_id, c.input_hash, c.available_at.isoformat()) for c in curves],
            "mappings": mapping_payload,
            "points": [{
                "trading_date": point.trading_date.isoformat(),
                "source_contract": point.source_contract,
                "source_contract_id": source_ids[point.source_contract],
                "raw_settlement": str(point.raw_settlement),
                "adjusted_settlement": str(point.adjusted_settlement),
                "adjustment_value": str(point.cumulative_adjustment),
                "roll_flag": point.roll_flag,
                "research_index": str(research.index_value) if research.index_value is not None else None,
                "source_available_at": by_date[point.trading_date].available_at.isoformat(),
            } for point, research in zip(adjusted, index)],
        }
        snapshot_hash = stable_payload_hash(payload)
        snapshot_id = f"cont-{instrument.instrument_id}-{snapshot_hash[:48]}"
        repository.save_series_snapshot(
            snapshot_id=snapshot_id, instrument_id=instrument.instrument_id,
            series_type="back_adjusted", calculation_version="continuous_v1",
            input_hash=snapshot_hash, available_at=cutoff, payload=payload,
        )
        # Mapping rows remain available for operational inspection. The snapshot's
        # full mapping timeline is authoritative for revised point-in-time reads.
        for item in mapping_payload:
            repository.save_contract_mapping(
                mapping_id=f"map-{instrument.instrument_id}-{item['decision_date']}",
                instrument_id=instrument.instrument_id, to_contract_id=item["to_contract_id"],
                decision_date=date.fromisoformat(item["decision_date"]),
                effective_session=date.fromisoformat(item["effective_session"]),
                action=item["action"], available_at=cutoff,
            )
        for gap in gaps:
            repository.save_roll_event(
                instrument_id=instrument.instrument_id, from_contract_id=source_ids[gap.from_contract],
                to_contract_id=source_ids[gap.to_contract], decision_date=gap.effective_date,
                effective_date=gap.effective_date, from_settlement=gap.from_settlement,
                to_settlement=gap.to_settlement, adjustment_value=gap.additive_gap,
                available_at=cutoff,
            )
        report = MappingBuildReport(instrument.instrument_id, len(records), len(records), len(gaps), len(adjusted),
                                    sum(r.action is MappingAction.BLOCKED for r in records))
    return report
