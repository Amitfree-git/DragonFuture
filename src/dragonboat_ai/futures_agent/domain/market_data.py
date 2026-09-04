from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from .models import AnalysisRequest




@dataclass(frozen=True, slots=True)
class InstrumentRef:
    instrument_id: int
    exchange: str
    symbol: str
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ContractRef:
    instrument_id: int
    contract_id: int
    exchange: str
    symbol: str
    contract_code: str
    listed_date: date | None
    last_trade_date: date | None
    expiry_date: date


@dataclass(frozen=True, slots=True)
class ContractCandidate:
    contract: ContractRef
    trading_date: date
    settlement: Decimal
    volume: int
    open_interest: int
    days_to_expiry: int
    volume_share: float
    open_interest_share: float


@dataclass(frozen=True, slots=True)
class DailyBar:
    contract_id: int
    contract: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    settlement: Decimal
    previous_settlement: Decimal | None
    volume: int
    turnover: Decimal | None
    open_interest: int
    upper_limit: Decimal | None
    lower_limit: Decimal | None
    revision_no: int
    available_at: datetime
    source: str
    payload_hash: str


@dataclass(frozen=True, slots=True)
class ContinuousBar:
    instrument_id: int
    symbol: str
    trading_date: date
    source_contract_id: int
    source_contract: str
    raw_settlement: Decimal
    adjusted_settlement: Decimal
    adjustment_value: Decimal
    roll_flag: bool
    available_at: datetime
    input_hash: str


@dataclass(frozen=True, slots=True)
class CurvePoint:
    contract_id: int
    contract: str
    expiry_date: date
    days_to_expiry: int
    settlement: Decimal
    volume: int
    open_interest: int


@dataclass(frozen=True, slots=True)
class CurveSnapshot:
    snapshot_id: str
    instrument_id: int
    exchange: str
    symbol: str
    trading_date: date
    observed_at: datetime
    available_at: datetime
    points: tuple[CurvePoint, ...]
    source: str
    input_hash: str


@dataclass(frozen=True, slots=True)
class MarketContext:
    request: AnalysisRequest
    instrument_id: int
    contract_id: int
    exchange: str
    symbol: str
    selected_contract: str

    contract_bars: tuple[DailyBar, ...]
    continuous_bars: tuple[ContinuousBar, ...]
    current_curve: CurveSnapshot | None
    historical_curves: tuple[CurveSnapshot, ...]

    days_to_expiry: int
    recent_roll_date: date | None
    contract_selection_reason: str
    input_data_hash: str

    @property
    def source_contracts(self) -> tuple[str, ...]:
        contracts = {bar.source_contract for bar in self.continuous_bars}
        contracts.add(self.selected_contract)
        return tuple(sorted(contracts))
