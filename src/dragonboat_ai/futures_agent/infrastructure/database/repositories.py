from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from dragonboat_ai.futures_agent.domain.exceptions import DataNotFoundError, PersistenceError
from dragonboat_ai.futures_agent.domain.market_data import (
    ContractCandidate,
    ContractRef,
    ContinuousBar,
    CurvePoint,
    CurveSnapshot,
    DailyBar,
    InstrumentRef,
)
from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis

from .base import from_db_datetime, to_db_datetime
from .models import (
    FutAnalysisAuditLogORM,
    FutAnalysisEvidenceORM,
    FutAnalysisRunORM,
    FutBarDailyORM,
    FutContinuousBarDailyORM,
    FutContractORM,
    FutCurvePointORM,
    FutCurveSnapshotORM,
    FutDataBatchORM,
    FutFactorSnapshotORM,
    FutFeatureSnapshotORM,
    FutFeatureValueORM,
    FutInstrumentORM,
    FutInvalidationRuleORM,
    FutRollEventORM,
)


class SqlAlchemyMarketDataRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def get_or_create_instrument(
        self,
        *,
        exchange: str,
        symbol: str,
        name: str | None = None,
    ) -> int:
        exchange = exchange.upper()
        symbol = symbol.upper()
        with self.session_factory.begin() as session:
            row = session.scalar(
                select(FutInstrumentORM).where(
                    FutInstrumentORM.exchange == exchange,
                    FutInstrumentORM.symbol == symbol,
                )
            )
            if row is None:
                row = FutInstrumentORM(exchange=exchange, symbol=symbol, name=name)
                session.add(row)
                session.flush()
            return row.instrument_id

    def get_or_create_contract(
        self,
        *,
        instrument_id: int,
        contract_code: str,
        expiry_date: date,
        listed_date: date | None = None,
        last_trade_date: date | None = None,
        delivery_month: str | None = None,
    ) -> ContractRef:
        contract_code = contract_code.upper()
        with self.session_factory.begin() as session:
            row = session.scalar(
                select(FutContractORM).where(
                    FutContractORM.instrument_id == instrument_id,
                    FutContractORM.contract_code == contract_code,
                )
            )
            if row is None:
                row = FutContractORM(
                    instrument_id=instrument_id,
                    contract_code=contract_code,
                    expiry_date=expiry_date,
                    listed_date=listed_date,
                    last_trade_date=last_trade_date,
                    delivery_month=delivery_month,
                )
                session.add(row)
                session.flush()
            instrument = session.get(FutInstrumentORM, instrument_id)
            if instrument is None:
                raise PersistenceError(f"Instrument {instrument_id} does not exist")
            return self._contract_ref(row, instrument)

    def resolve_instrument(
        self,
        *,
        symbol: str,
        exchange: str | None = None,
    ) -> InstrumentRef:
        symbol = symbol.upper()
        with self.session_factory() as session:
            stmt = select(FutInstrumentORM).where(FutInstrumentORM.symbol == symbol)
            if exchange:
                stmt = stmt.where(FutInstrumentORM.exchange == exchange.upper())
            rows = session.scalars(stmt).all()
            if len(rows) != 1:
                raise DataNotFoundError(
                    f"Expected one instrument for {symbol}; found {len(rows)}"
                )
            row = rows[0]
            return InstrumentRef(
                instrument_id=row.instrument_id,
                exchange=row.exchange,
                symbol=row.symbol,
                name=row.name,
            )

    def resolve_contract(
        self,
        *,
        symbol: str,
        contract_code: str,
        exchange: str | None = None,
    ) -> ContractRef:
        symbol = symbol.upper()
        contract_code = contract_code.upper()
        with self.session_factory() as session:
            stmt = (
                select(FutContractORM, FutInstrumentORM)
                .join(FutInstrumentORM, FutContractORM.instrument_id == FutInstrumentORM.instrument_id)
                .where(
                    FutInstrumentORM.symbol == symbol,
                    FutContractORM.contract_code == contract_code,
                )
            )
            if exchange:
                stmt = stmt.where(FutInstrumentORM.exchange == exchange.upper())
            rows = session.execute(stmt).all()
            if len(rows) != 1:
                raise DataNotFoundError(
                    f"Expected one contract for {symbol}/{contract_code}; found {len(rows)}"
                )
            contract, instrument = rows[0]
            return self._contract_ref(contract, instrument)

    def add_daily_bar(self, bar: DailyBar, *, data_batch_id: str | None = None) -> None:
        with self.session_factory.begin() as session:
            session.add(
                FutBarDailyORM(
                    contract_id=bar.contract_id,
                    trading_date=bar.trading_date,
                    open_price=bar.open,
                    high_price=bar.high,
                    low_price=bar.low,
                    close_price=bar.close,
                    settlement_price=bar.settlement,
                    previous_settlement=bar.previous_settlement,
                    volume=bar.volume,
                    turnover=bar.turnover,
                    open_interest=bar.open_interest,
                    upper_limit=bar.upper_limit,
                    lower_limit=bar.lower_limit,
                    source=bar.source,
                    revision_no=bar.revision_no,
                    available_at=to_db_datetime(bar.available_at),
                    published_at=to_db_datetime(bar.published_at) if bar.published_at else None,
                    received_at=to_db_datetime(bar.received_at) if bar.received_at else None,
                    data_mode=bar.data_mode,
                    data_batch_id=data_batch_id or bar.data_batch_id,
                    payload_hash=bar.payload_hash,
                )
            )

    def add_continuous_bar(
        self,
        bar: ContinuousBar,
        *,
        series_type: str = "back_adjusted",
        adjustment_method: str = "backward_additive",
        roll_rule_version: str = "main_contract_v1",
        calculation_version: str = "continuous_v1",
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                FutContinuousBarDailyORM(
                    instrument_id=bar.instrument_id,
                    series_type=series_type,
                    trading_date=bar.trading_date,
                    source_contract_id=bar.source_contract_id,
                    raw_settlement=bar.raw_settlement,
                    adjusted_settlement=bar.adjusted_settlement,
                    adjustment_method=adjustment_method,
                    cumulative_adjustment=bar.adjustment_value,
                    roll_flag=bar.roll_flag,
                    roll_rule_version=roll_rule_version,
                    calculation_version=calculation_version,
                    available_at=to_db_datetime(bar.available_at),
                    input_hash=bar.input_hash,
                )
            )

    def add_curve_snapshot(self, snapshot: CurveSnapshot, *, revision_no: int = 1) -> None:
        with self.session_factory.begin() as session:
            session.add(
                FutCurveSnapshotORM(
                    snapshot_id=snapshot.snapshot_id,
                    instrument_id=snapshot.instrument_id,
                    trading_date=snapshot.trading_date,
                    observed_at=to_db_datetime(snapshot.observed_at),
                    available_at=to_db_datetime(snapshot.available_at),
                    source=snapshot.source,
                    revision_no=revision_no,
                    input_hash=snapshot.input_hash,
                )
            )
            # Explicit flush guarantees parent visibility for SQLite foreign-key
            # enforcement even though ORM relationships are intentionally omitted.
            session.flush()
            for sequence, point in enumerate(sorted(snapshot.points, key=lambda item: item.days_to_expiry), 1):
                session.add(
                    FutCurvePointORM(
                        snapshot_id=snapshot.snapshot_id,
                        contract_id=point.contract_id,
                        sequence_no=sequence,
                        days_to_expiry=point.days_to_expiry,
                        settlement_price=point.settlement,
                        volume=point.volume,
                        open_interest=point.open_interest,
                    )
                )

    def load_contract_bars(
        self,
        *,
        contract_id: int,
        as_of: datetime,
        limit: int = 400,
    ) -> tuple[DailyBar, ...]:
        cutoff = to_db_datetime(as_of)
        ranked = (
            select(
                FutBarDailyORM.bar_id.label("bar_id"),
                func.row_number()
                .over(
                    partition_by=FutBarDailyORM.trading_date,
                    order_by=(FutBarDailyORM.available_at.desc(), FutBarDailyORM.revision_no.desc()),
                )
                .label("revision_rank"),
            )
            .outerjoin(FutDataBatchORM, FutBarDailyORM.data_batch_id == FutDataBatchORM.batch_id)
            .where(
                FutBarDailyORM.contract_id == contract_id,
                FutBarDailyORM.available_at <= cutoff,
                or_(
                    FutBarDailyORM.data_batch_id.is_(None),
                    FutDataBatchORM.status == "committed",
                ),
            )
            .subquery()
        )
        stmt = (
            select(FutBarDailyORM, FutContractORM.contract_code)
            .join(ranked, FutBarDailyORM.bar_id == ranked.c.bar_id)
            .join(FutContractORM, FutBarDailyORM.contract_id == FutContractORM.contract_id)
            .where(ranked.c.revision_rank == 1)
            .order_by(FutBarDailyORM.trading_date.desc())
            .limit(limit)
        )
        with self.session_factory() as session:
            rows = list(reversed(session.execute(stmt).all()))
            return tuple(self._daily_bar(row, code) for row, code in rows)

    def load_continuous_bars(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
        limit: int = 500,
        calculation_version: str = "continuous_v1",
    ) -> tuple[ContinuousBar, ...]:
        stmt = (
            select(FutContinuousBarDailyORM, FutContractORM.contract_code, FutInstrumentORM.symbol)
            .join(FutContractORM, FutContinuousBarDailyORM.source_contract_id == FutContractORM.contract_id)
            .join(FutInstrumentORM, FutContinuousBarDailyORM.instrument_id == FutInstrumentORM.instrument_id)
            .where(
                FutContinuousBarDailyORM.instrument_id == instrument_id,
                FutContinuousBarDailyORM.calculation_version == calculation_version,
                FutContinuousBarDailyORM.available_at <= to_db_datetime(as_of),
            )
            .order_by(FutContinuousBarDailyORM.trading_date.desc())
            .limit(limit)
        )
        with self.session_factory() as session:
            rows = list(reversed(session.execute(stmt).all()))
            return tuple(
                ContinuousBar(
                    instrument_id=row.instrument_id,
                    symbol=symbol,
                    trading_date=row.trading_date,
                    source_contract_id=row.source_contract_id,
                    source_contract=contract_code,
                    raw_settlement=row.raw_settlement,
                    adjusted_settlement=row.adjusted_settlement,
                    adjustment_value=row.cumulative_adjustment,
                    roll_flag=row.roll_flag,
                    available_at=from_db_datetime(row.available_at),
                    input_hash=row.input_hash,
                )
                for row, contract_code, symbol in rows
            )

    def load_curve_snapshots(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
        limit: int = 400,
    ) -> tuple[CurveSnapshot, ...]:
        cutoff = to_db_datetime(as_of)
        ranked = (
            select(
                FutCurveSnapshotORM.snapshot_id.label("snapshot_id"),
                func.row_number()
                .over(
                    partition_by=FutCurveSnapshotORM.trading_date,
                    order_by=(
                        FutCurveSnapshotORM.available_at.desc(),
                        FutCurveSnapshotORM.revision_no.desc(),
                    ),
                )
                .label("revision_rank"),
            )
            .where(
                FutCurveSnapshotORM.instrument_id == instrument_id,
                FutCurveSnapshotORM.available_at <= cutoff,
            )
            .subquery()
        )
        stmt = (
            select(FutCurveSnapshotORM, FutInstrumentORM)
            .join(ranked, FutCurveSnapshotORM.snapshot_id == ranked.c.snapshot_id)
            .join(FutInstrumentORM, FutCurveSnapshotORM.instrument_id == FutInstrumentORM.instrument_id)
            .where(ranked.c.revision_rank == 1)
            .order_by(FutCurveSnapshotORM.trading_date.desc())
            .limit(limit)
        )
        with self.session_factory() as session:
            snapshot_rows = session.execute(stmt).all()
            if not snapshot_rows:
                return ()
            ids = [row.snapshot_id for row, _ in snapshot_rows]
            point_stmt = (
                select(FutCurvePointORM, FutContractORM)
                .join(FutContractORM, FutCurvePointORM.contract_id == FutContractORM.contract_id)
                .where(FutCurvePointORM.snapshot_id.in_(ids))
                .order_by(FutCurvePointORM.snapshot_id, FutCurvePointORM.sequence_no)
            )
            points_by_snapshot: dict[str, list[CurvePoint]] = defaultdict(list)
            for point, contract in session.execute(point_stmt):
                points_by_snapshot[point.snapshot_id].append(
                    CurvePoint(
                        contract_id=point.contract_id,
                        contract=contract.contract_code,
                        expiry_date=contract.expiry_date,
                        days_to_expiry=point.days_to_expiry,
                        settlement=point.settlement_price,
                        volume=point.volume,
                        open_interest=point.open_interest,
                    )
                )
            snapshots = [
                CurveSnapshot(
                    snapshot_id=row.snapshot_id,
                    instrument_id=row.instrument_id,
                    exchange=instrument.exchange,
                    symbol=instrument.symbol,
                    trading_date=row.trading_date,
                    observed_at=from_db_datetime(row.observed_at),
                    available_at=from_db_datetime(row.available_at),
                    points=tuple(points_by_snapshot[row.snapshot_id]),
                    source=row.source,
                    input_hash=row.input_hash,
                )
                for row, instrument in snapshot_rows
            ]
            return tuple(sorted(snapshots, key=lambda item: item.trading_date))

    def candidates_from_curve(self, snapshot: CurveSnapshot) -> list[ContractCandidate]:
        total_volume = sum(max(point.volume, 0) for point in snapshot.points)
        total_oi = sum(max(point.open_interest, 0) for point in snapshot.points)
        candidates: list[ContractCandidate] = []
        with self.session_factory() as session:
            instrument = session.get(FutInstrumentORM, snapshot.instrument_id)
            if instrument is None:
                raise DataNotFoundError(f"Instrument {snapshot.instrument_id} not found")
            contract_rows = {
                row.contract_id: row
                for row in session.scalars(
                    select(FutContractORM).where(
                        FutContractORM.contract_id.in_([point.contract_id for point in snapshot.points])
                    )
                )
            }
            for point in snapshot.points:
                row = contract_rows[point.contract_id]
                candidates.append(
                    ContractCandidate(
                        contract=self._contract_ref(row, instrument),
                        trading_date=snapshot.trading_date,
                        settlement=point.settlement,
                        volume=point.volume,
                        open_interest=point.open_interest,
                        days_to_expiry=point.days_to_expiry,
                        volume_share=point.volume / total_volume if total_volume > 0 else 0.0,
                        open_interest_share=point.open_interest / total_oi if total_oi > 0 else 0.0,
                    )
                )
        return candidates

    def latest_roll_date(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
    ) -> date | None:
        stmt = select(func.max(FutRollEventORM.effective_date)).where(
            FutRollEventORM.instrument_id == instrument_id,
            FutRollEventORM.effective_date <= as_of.date(),
            FutRollEventORM.available_at <= to_db_datetime(as_of),
        )
        with self.session_factory() as session:
            return session.scalar(stmt)

    @staticmethod
    def _contract_ref(row: FutContractORM, instrument: FutInstrumentORM) -> ContractRef:
        return ContractRef(
            instrument_id=instrument.instrument_id,
            contract_id=row.contract_id,
            exchange=instrument.exchange,
            symbol=instrument.symbol,
            contract_code=row.contract_code,
            listed_date=row.listed_date,
            last_trade_date=row.last_trade_date,
            expiry_date=row.expiry_date,
            tradable_until=row.tradable_until,
        )

    @staticmethod
    def _daily_bar(row: FutBarDailyORM, contract_code: str) -> DailyBar:
        return DailyBar(
            contract_id=row.contract_id,
            contract=contract_code,
            trading_date=row.trading_date,
            open=row.open_price,
            high=row.high_price,
            low=row.low_price,
            close=row.close_price,
            settlement=row.settlement_price,
            previous_settlement=row.previous_settlement,
            volume=row.volume,
            turnover=row.turnover,
            open_interest=row.open_interest,
            upper_limit=row.upper_limit,
            lower_limit=row.lower_limit,
            revision_no=row.revision_no,
            available_at=from_db_datetime(row.available_at),
            source=row.source,
            payload_hash=row.payload_hash,
            published_at=from_db_datetime(row.published_at) if row.published_at else None,
            received_at=from_db_datetime(row.received_at) if row.received_at else None,
            data_mode=row.data_mode or "final_only",
            data_batch_id=row.data_batch_id,
        )


class SqlAlchemyAnalysisRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def find_cached(
        self,
        *,
        request_hash: str,
        input_data_hash: str,
        version_hash: str,
    ) -> FuturesMarketAnalysis | None:
        stmt = (
            select(FutAnalysisRunORM)
            .where(
                FutAnalysisRunORM.request_hash == request_hash,
                FutAnalysisRunORM.input_data_hash == input_data_hash,
                FutAnalysisRunORM.version_hash == version_hash,
                FutAnalysisRunORM.status == "completed",
            )
            .order_by(FutAnalysisRunORM.created_at.desc())
            .limit(1)
        )
        with self.session_factory() as session:
            row = session.scalar(stmt)
            return self._to_domain(row) if row else None

    def get(self, analysis_id: str) -> FuturesMarketAnalysis | None:
        with self.session_factory() as session:
            row = session.get(FutAnalysisRunORM, analysis_id)
            return self._to_domain(row) if row else None

    def latest(self, symbol: str, horizon: str) -> FuturesMarketAnalysis | None:
        stmt = (
            select(FutAnalysisRunORM)
            .where(
                FutAnalysisRunORM.symbol == symbol.upper(),
                FutAnalysisRunORM.horizon == horizon,
                FutAnalysisRunORM.status == "completed",
            )
            .order_by(FutAnalysisRunORM.as_of.desc(), FutAnalysisRunORM.created_at.desc())
            .limit(1)
        )
        with self.session_factory() as session:
            row = session.scalar(stmt)
            return self._to_domain(row) if row else None

    def save(
        self,
        analysis: FuturesMarketAnalysis,
        *,
        version_hash: str,
    ) -> FuturesMarketAnalysis:
        with self.session_factory.begin() as session:
            instrument_stmt = select(FutInstrumentORM).where(
                FutInstrumentORM.symbol == analysis.request.symbol
            )
            if analysis.request.exchange:
                instrument_stmt = instrument_stmt.where(
                    FutInstrumentORM.exchange == analysis.request.exchange
                )
            instruments = session.scalars(instrument_stmt).all()
            if len(instruments) != 1:
                raise PersistenceError(
                    f"Cannot persist analysis: expected one instrument, found {len(instruments)}"
                )
            instrument = instruments[0]
            contract = session.scalar(
                select(FutContractORM).where(
                    FutContractORM.instrument_id == instrument.instrument_id,
                    FutContractORM.contract_code == analysis.selected_contract,
                )
            )
            if contract is None:
                raise PersistenceError(f"Contract {analysis.selected_contract} is not registered")

            existing = session.scalar(
                select(FutAnalysisRunORM).where(
                    FutAnalysisRunORM.request_hash == analysis.request_hash,
                    FutAnalysisRunORM.input_data_hash == analysis.input_data_hash,
                    FutAnalysisRunORM.version_hash == version_hash,
                )
            )
            if existing is not None:
                return self._to_domain(existing)

            feature_snapshot_id = self._persist_feature_and_factor_snapshots(
                session=session,
                analysis=analysis,
                instrument_id=instrument.instrument_id,
                contract_id=contract.contract_id,
            )

            payload = analysis.model_dump(mode="json", exclude={"narrative"})
            narrative = analysis.narrative.model_dump(mode="json") if analysis.narrative else None
            row = FutAnalysisRunORM(
                analysis_id=analysis.analysis_id,
                request_hash=analysis.request_hash,
                input_data_hash=analysis.input_data_hash,
                version_hash=version_hash,
                core_result_hash=analysis.core_result_hash,
                instrument_id=instrument.instrument_id,
                contract_id=contract.contract_id,
                exchange=instrument.exchange,
                symbol=instrument.symbol,
                contract_code=contract.contract_code,
                as_of=to_db_datetime(analysis.request.as_of),
                horizon=analysis.request.horizon.value,
                direction_score=analysis.direction.score,
                opportunity_score=analysis.opportunity.score,
                confidence_score=analysis.confidence.score,
                risk_score=analysis.risk.score,
                direction_label=analysis.direction.label.value,
                opportunity_action=analysis.opportunity.action.value,
                primary_regime=analysis.regime.primary,
                schema_version=analysis.versions.schema_version,
                data_version=analysis.versions.data_version,
                feature_set_version=analysis.versions.feature_set_version,
                factor_model_version=analysis.versions.factor_model_version,
                score_config_version=analysis.versions.score_config_version,
                score_config_hash=analysis.versions.score_config_hash,
                regime_rule_version=analysis.versions.regime_rule_version,
                prompt_version=analysis.versions.prompt_version,
                code_commit=analysis.versions.code_commit,
                core_result_json=payload,
                narrative_json=narrative,
                status="completed",
            )
            session.add(row)
            # Flush the analysis parent before inserting evidence/audit children.
            session.flush()
            for evidence in analysis.evidence:
                session.add(
                    FutAnalysisEvidenceORM(
                        analysis_id=analysis.analysis_id,
                        evidence_id=evidence.evidence_id,
                        factor=evidence.factor.value,
                        stance=evidence.stance.value,
                        kind=evidence.kind.value,
                        strength=evidence.strength,
                        claim=evidence.claim,
                        evidence_json=evidence.model_dump(mode="json"),
                    )
                )
            for condition in analysis.invalidation_conditions:
                session.add(
                    FutInvalidationRuleORM(
                        analysis_id=analysis.analysis_id,
                        condition_id=condition.condition_id,
                        condition_json=condition.model_dump(mode="json"),
                    )
                )
            session.add(
                FutAnalysisAuditLogORM(
                    analysis_id=analysis.analysis_id,
                    action="analysis_persisted",
                    actor="futures_market_analyst",
                    details_json={
                        "core_result_hash": analysis.core_result_hash,
                        "feature_snapshot_id": feature_snapshot_id,
                        "version_hash": version_hash,
                    },
                )
            )
        return analysis

    @staticmethod
    def _persist_feature_and_factor_snapshots(
        *,
        session: Session,
        analysis: FuturesMarketAnalysis,
        instrument_id: int,
        contract_id: int,
    ) -> str:
        as_of = to_db_datetime(analysis.request.as_of)
        feature_stmt = select(FutFeatureSnapshotORM).where(
            FutFeatureSnapshotORM.instrument_id == instrument_id,
            FutFeatureSnapshotORM.contract_id == contract_id,
            FutFeatureSnapshotORM.as_of == as_of,
            FutFeatureSnapshotORM.horizon == analysis.request.horizon.value,
            FutFeatureSnapshotORM.feature_set_version
            == analysis.versions.feature_set_version,
            FutFeatureSnapshotORM.input_data_hash == analysis.input_data_hash,
        )
        snapshot = session.scalar(feature_stmt)
        if snapshot is None:
            identity = "|".join(
                (
                    str(instrument_id),
                    str(contract_id),
                    analysis.request.as_of.isoformat(),
                    analysis.request.horizon.value,
                    analysis.versions.feature_set_version,
                    analysis.input_data_hash,
                )
            )
            snapshot_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            snapshot = FutFeatureSnapshotORM(
                snapshot_id=snapshot_id,
                instrument_id=instrument_id,
                contract_id=contract_id,
                as_of=as_of,
                horizon=analysis.request.horizon.value,
                feature_set_version=analysis.versions.feature_set_version,
                normalization_version="robust_percentile_tanh_v1",
                input_data_hash=analysis.input_data_hash,
                status=analysis.data_quality.status.value,
            )
            session.add(snapshot)
            session.flush()
            for metric in analysis.metrics.values():
                session.add(
                    FutFeatureValueORM(
                        snapshot_id=snapshot_id,
                        feature_name=metric.name,
                        value_numeric=metric.value,
                        value_text=None,
                        unit=metric.unit,
                        zscore=metric.zscore,
                        percentile=metric.percentile,
                        normalized_score=metric.normalized_score,
                        lookback_window=metric.lookback,
                        observation_count=None,
                        quality_score=metric.quality_score,
                        status=metric.status.value,
                        source_reference=metric.source,
                    )
                )
        else:
            snapshot_id = snapshot.snapshot_id

        for factor in analysis.factors:
            factor_key = (
                snapshot_id,
                factor.factor.value,
                analysis.versions.factor_model_version,
                analysis.versions.score_config_version,
                analysis.versions.score_config_hash,
            )
            if session.get(FutFactorSnapshotORM, factor_key) is not None:
                continue
            session.add(
                FutFactorSnapshotORM(
                    snapshot_id=snapshot_id,
                    factor_name=factor.factor.value,
                    factor_model_version=analysis.versions.factor_model_version,
                    score_config_version=analysis.versions.score_config_version,
                    score_config_hash=analysis.versions.score_config_hash,
                    score=factor.score,
                    coverage=factor.coverage,
                    confidence=factor.confidence,
                    status=factor.status.value,
                    contribution_json=[
                        contribution.model_dump(mode="json")
                        for contribution in factor.contributions
                    ],
                )
            )
        return snapshot_id

    @staticmethod
    def _to_domain(row: FutAnalysisRunORM) -> FuturesMarketAnalysis:
        payload = dict(row.core_result_json)
        payload["narrative"] = row.narrative_json
        return FuturesMarketAnalysis.model_validate(payload)


def stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
