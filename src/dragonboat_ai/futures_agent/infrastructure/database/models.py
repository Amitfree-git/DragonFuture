from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utc_now_naive

PRICE_TYPE = Numeric(24, 8)


class FutInstrumentORM(Base):
    __tablename__ = "fut_instrument"
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_fut_instrument_exchange_symbol"),
    )

    instrument_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False, default="commodity")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="CNY")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutContractORM(Base):
    __tablename__ = "fut_contract"
    __table_args__ = (
        UniqueConstraint("instrument_id", "contract_code", name="uq_fut_contract_instrument_code"),
        Index("ix_fut_contract_code", "contract_code"),
    )

    contract_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("fut_instrument.instrument_id", ondelete="CASCADE"), nullable=False
    )
    contract_code: Mapped[str] = mapped_column(String(32), nullable=False)
    listed_date: Mapped[date | None] = mapped_column(Date)
    last_trade_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_month: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutContractSpecORM(Base):
    __tablename__ = "fut_contract_spec"
    __table_args__ = (
        UniqueConstraint("contract_id", "effective_from", name="uq_fut_contract_spec_effective"),
    )

    spec_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("fut_contract.contract_id", ondelete="CASCADE"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    multiplier: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    tick_size: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    margin_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    trading_unit: Mapped[str | None] = mapped_column(String(64))


class FutDataBatchORM(Base):
    __tablename__ = "fut_data_batch"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class FutBarDailyORM(Base):
    __tablename__ = "fut_bar_daily"
    __table_args__ = (
        UniqueConstraint(
            "contract_id", "trading_date", "source", "revision_no",
            name="uq_fut_bar_daily_revision",
        ),
        CheckConstraint("high_price >= low_price", name="high_ge_low"),
        CheckConstraint("volume >= 0", name="volume_nonnegative"),
        CheckConstraint("open_interest >= 0", name="oi_nonnegative"),
        Index("ix_fut_bar_contract_date", "contract_id", "trading_date"),
        Index("ix_fut_bar_point_in_time", "contract_id", "trading_date", "available_at"),
    )

    bar_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("fut_contract.contract_id", ondelete="CASCADE"), nullable=False
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    high_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    low_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    close_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    settlement_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    previous_settlement: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False)
    upper_limit: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    lower_limit: Mapped[Decimal | None] = mapped_column(PRICE_TYPE)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)
    data_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("fut_data_batch.batch_id", ondelete="SET NULL")
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class FutContractRankDailyORM(Base):
    __tablename__ = "fut_contract_rank_daily"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "contract_id", "trading_date", "calculation_version",
            name="uq_fut_contract_rank_daily",
        ),
        Index("ix_fut_contract_rank_instrument_date", "instrument_id", "trading_date"),
    )

    rank_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("fut_instrument.instrument_id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("fut_contract.contract_id", ondelete="CASCADE"), nullable=False
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    volume_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_share: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    open_interest_share: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class FutRollEventORM(Base):
    __tablename__ = "fut_roll_event"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "effective_date", "roll_rule_version",
            name="uq_fut_roll_event_effective",
        ),
    )

    roll_event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("fut_instrument.instrument_id", ondelete="CASCADE"), nullable=False
    )
    from_contract_id: Mapped[int] = mapped_column(ForeignKey("fut_contract.contract_id"), nullable=False)
    to_contract_id: Mapped[int] = mapped_column(ForeignKey("fut_contract.contract_id"), nullable=False)
    decision_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_settlement: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    to_settlement: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    adjustment_value: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    roll_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutContinuousBarDailyORM(Base):
    __tablename__ = "fut_continuous_bar_daily"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "series_type", "trading_date", "calculation_version",
            name="uq_fut_continuous_bar_daily",
        ),
        Index("ix_fut_continuous_instrument_date", "instrument_id", "trading_date"),
        Index("ix_fut_continuous_point_in_time", "instrument_id", "trading_date", "available_at"),
    )

    continuous_bar_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("fut_instrument.instrument_id", ondelete="CASCADE"), nullable=False
    )
    series_type: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_contract_id: Mapped[int] = mapped_column(
        ForeignKey("fut_contract.contract_id"), nullable=False
    )
    raw_settlement: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    adjusted_settlement: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    adjustment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    cumulative_adjustment: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    roll_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    roll_event_id: Mapped[int | None] = mapped_column(ForeignKey("fut_roll_event.roll_event_id"))
    roll_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class FutCurveSnapshotORM(Base):
    __tablename__ = "fut_curve_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "trading_date", "source", "revision_no",
            name="uq_fut_curve_snapshot_revision",
        ),
        Index("ix_fut_curve_point_in_time", "instrument_id", "trading_date", "available_at"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("fut_instrument.instrument_id", ondelete="CASCADE"), nullable=False
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutCurvePointORM(Base):
    __tablename__ = "fut_curve_point"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "contract_id", name="uq_fut_curve_point_contract"),
    )

    curve_point_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("fut_curve_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("fut_contract.contract_id", ondelete="CASCADE"), nullable=False
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    days_to_expiry: Mapped[int] = mapped_column(Integer, nullable=False)
    settlement_price: Mapped[Decimal] = mapped_column(PRICE_TYPE, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    open_interest: Mapped[int] = mapped_column(Integer, nullable=False)


class FutFeatureSnapshotORM(Base):
    __tablename__ = "fut_feature_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id", "contract_id", "as_of", "horizon", "feature_set_version", "input_data_hash",
            name="uq_fut_feature_snapshot_identity",
        ),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("fut_instrument.instrument_id"), nullable=False)
    contract_id: Mapped[int] = mapped_column(ForeignKey("fut_contract.contract_id"), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutFeatureValueORM(Base):
    __tablename__ = "fut_feature_value"

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("fut_feature_snapshot.snapshot_id", ondelete="CASCADE"), primary_key=True
    )
    feature_name: Mapped[str] = mapped_column(String(96), primary_key=True)
    value_numeric: Mapped[float | None] = mapped_column(Numeric(28, 12))
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(48))
    zscore: Mapped[float | None] = mapped_column(Numeric(18, 8))
    percentile: Mapped[float | None] = mapped_column(Numeric(12, 8))
    normalized_score: Mapped[float | None] = mapped_column(Numeric(12, 8))
    lookback_window: Mapped[int | None] = mapped_column(Integer)
    observation_count: Mapped[int | None] = mapped_column(Integer)
    quality_score: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)


class FutFactorSnapshotORM(Base):
    __tablename__ = "fut_factor_snapshot"

    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("fut_feature_snapshot.snapshot_id", ondelete="CASCADE"), primary_key=True
    )
    factor_name: Mapped[str] = mapped_column(String(48), primary_key=True)
    factor_model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    score_config_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    score_config_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[float | None] = mapped_column(Numeric(12, 8))
    coverage: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    contribution_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)


class FutAnalysisRunORM(Base):
    __tablename__ = "fut_analysis_run"
    __table_args__ = (
        UniqueConstraint(
            "request_hash", "input_data_hash", "version_hash",
            name="uq_fut_analysis_run_identity",
        ),
        Index("ix_fut_analysis_symbol_as_of", "symbol", "as_of"),
    )

    analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    core_result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("fut_instrument.instrument_id"), nullable=False)
    contract_id: Mapped[int] = mapped_column(ForeignKey("fut_contract.contract_id"), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    contract_code: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False)
    direction_score: Mapped[float | None] = mapped_column(Numeric(12, 8))
    opportunity_score: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    risk_score: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    direction_label: Mapped[str] = mapped_column(String(32), nullable=False)
    opportunity_action: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_regime: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    data_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    factor_model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    score_config_version: Mapped[str] = mapped_column(String(64), nullable=False)
    score_config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    regime_rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    code_commit: Mapped[str | None] = mapped_column(String(64))
    core_result_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    narrative_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutAnalysisEvidenceORM(Base):
    __tablename__ = "fut_analysis_evidence"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("fut_analysis_run.analysis_id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factor: Mapped[str] = mapped_column(String(48), nullable=False)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    strength: Mapped[float] = mapped_column(Numeric(12, 8), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class FutInvalidationRuleORM(Base):
    __tablename__ = "fut_invalidation_rule"

    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("fut_analysis_run.analysis_id", ondelete="CASCADE"), primary_key=True
    )
    condition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    condition_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)


class FutInvalidationStateORM(Base):
    __tablename__ = "fut_invalidation_state"

    state_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    triggered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_value: Mapped[float | None] = mapped_column(Numeric(28, 12))
    state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["analysis_id", "condition_id"],
            ["fut_invalidation_rule.analysis_id", "fut_invalidation_rule.condition_id"],
            ondelete="CASCADE",
            name="fk_fut_invalidation_state_rule",
        ),
        Index("ix_fut_invalidation_state_analysis", "analysis_id", "evaluated_at"),
    )


class FutDataQualityIssueORM(Base):
    __tablename__ = "fut_data_quality_issue"

    issue_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("fut_data_batch.batch_id", ondelete="SET NULL"))
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("fut_instrument.instrument_id"))
    contract_id: Mapped[int | None] = mapped_column(ForeignKey("fut_contract.contract_id"))
    issue_code: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class FutModelVersionORM(Base):
    __tablename__ = "fut_model_version"
    __table_args__ = (
        UniqueConstraint("model_type", "version", name="uq_fut_model_version_type_version"),
    )

    model_version_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(48), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    code_commit: Mapped[str | None] = mapped_column(String(64))
    active_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    active_to: Mapped[datetime | None] = mapped_column(DateTime)


class FutAnalysisAuditLogORM(Base):
    __tablename__ = "fut_analysis_audit_log"
    __table_args__ = (
        Index("ix_fut_analysis_audit_analysis", "analysis_id", "occurred_at"),
    )

    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("fut_analysis_run.analysis_id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now_naive)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
