from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AnalysisHorizon,
    ContextName,
    DataStatus,
    DirectionLabel,
    EvidenceKind,
    FactorName,
    OpportunityAction,
    RiskLevel,
    Stance,
    TradeSide,
)

SignedScore = Annotated[float, Field(ge=-100.0, le=100.0)]
UnsignedScore = Annotated[float, Field(ge=0.0, le=100.0)]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


class AnalysisRequest(DomainModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str | None = Field(default=None, max_length=16)
    contract: str | None = Field(default=None, max_length=32)
    horizon: AnalysisHorizon = AnalysisHorizon.SWING
    as_of: datetime
    include_narrative: bool = True
    force_refresh: bool = False

    @field_validator("symbol", "exchange", "contract")
    @classmethod
    def normalize_codes(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else value

    @field_validator("as_of")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value


class MetricObservation(DomainModel):
    metric_id: str
    name: str
    value: float | None
    unit: str | None = None
    normalized_score: SignedScore | None = None

    observation_time: datetime
    available_at: datetime

    lookback: int | None = Field(default=None, ge=1)
    percentile: UnsignedScore | None = None
    zscore: float | None = None

    source: str
    quality_score: UnsignedScore = 100.0
    status: DataStatus = DataStatus.OK

    @field_validator("observation_time", "available_at")
    @classmethod
    def require_metric_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("metric timestamps must be timezone-aware")
        return value


class FeatureContribution(DomainModel):
    feature_name: str
    feature_score: SignedScore
    weight: float = Field(gt=0.0, le=1.0)
    weighted_contribution: float
    metric_ids: list[str] = Field(default_factory=list)


class Evidence(DomainModel):
    evidence_id: str
    factor: FactorName | ContextName
    stance: Stance
    kind: EvidenceKind
    strength: UnsignedScore
    claim: str
    metric_ids: list[str] = Field(default_factory=list)
    reasoning: str | None = None


class FactorAssessment(DomainModel):
    factor: FactorName
    status: DataStatus
    score: SignedScore | None = None
    coverage: UnsignedScore
    confidence: UnsignedScore
    contributions: list[FeatureContribution] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MarketRegime(DomainModel):
    primary: str
    secondary: list[str] = Field(default_factory=list)
    volatility_regime: str
    liquidity_regime: str
    regime_confidence: UnsignedScore
    hypothesis_labels: list[str] = Field(default_factory=list)


class DirectionAssessment(DomainModel):
    horizon: AnalysisHorizon
    score: SignedScore | None
    label: DirectionLabel
    available_factor_weight: UnsignedScore
    factor_scores: dict[str, float | None] = Field(default_factory=dict)


class ConfidenceAssessment(DomainModel):
    score: UnsignedScore
    data_coverage: UnsignedScore
    freshness: UnsignedScore
    factor_agreement: UnsignedScore
    data_quality: UnsignedScore
    historical_calibration: UnsignedScore | None = None


class RiskItem(DomainModel):
    risk_code: str
    severity: UnsignedScore
    description: str
    hard_gate: bool = False
    observed_value: float | None = None
    threshold: float | None = None
    metric_ids: list[str] = Field(default_factory=list)


class RiskAssessment(DomainModel):
    score: UnsignedScore
    level: RiskLevel
    hard_gate_triggered: bool
    items: list[RiskItem] = Field(default_factory=list)


class OpportunityAssessment(DomainModel):
    side: TradeSide
    action: OpportunityAction
    score: UnsignedScore
    entry_quality: UnsignedScore
    regime_fit: UnsignedScore
    liquidity_quality: UnsignedScore
    hard_gate_reasons: list[str] = Field(default_factory=list)


class InvalidationCondition(DomainModel):
    condition_id: str
    description: str
    metric_name: str
    operator: Literal["lt", "lte", "gt", "gte", "cross_below", "cross_above"]
    threshold: float
    value_field: Literal["value", "normalized_score"] = "value"
    lookback_bars: int = Field(default=1, ge=1)
    consecutive_bars: int = Field(default=1, ge=1)
    current_value: float | None = None
    triggered: bool = False
    severity_if_triggered: UnsignedScore = 50.0


class DataQualityAssessment(DomainModel):
    status: DataStatus
    overall_score: UnsignedScore
    required_data_coverage: UnsignedScore
    stale_sources: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AnalysisVersions(DomainModel):
    schema_version: str
    data_version: str
    feature_set_version: str
    factor_model_version: str
    score_config_version: str
    score_config_hash: str = ""
    regime_rule_version: str
    prompt_version: str | None = None
    code_commit: str | None = None


class NarrativeOutput(DomainModel):
    executive_summary: str
    market_structure: str
    bullish_case: list[str] = Field(default_factory=list)
    bearish_case: list[str] = Field(default_factory=list)
    conflict_analysis: list[str] = Field(default_factory=list)
    risk_summary: list[str] = Field(default_factory=list)
    invalidation_summary: list[str] = Field(default_factory=list)
    final_conclusion: str


class FuturesMarketAnalysis(DomainModel):
    analysis_id: str
    request_hash: str
    input_data_hash: str
    request: AnalysisRequest

    selected_contract: str
    source_contracts: list[str]

    generated_at: datetime
    data_cutoff: datetime

    data_quality: DataQualityAssessment
    factors: list[FactorAssessment]
    regime: MarketRegime
    direction: DirectionAssessment
    confidence: ConfidenceAssessment
    opportunity: OpportunityAssessment
    risk: RiskAssessment

    metrics: dict[str, MetricObservation] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    invalidation_conditions: list[InvalidationCondition] = Field(default_factory=list)

    versions: AnalysisVersions
    core_result_hash: str
    narrative: NarrativeOutput | None = None
