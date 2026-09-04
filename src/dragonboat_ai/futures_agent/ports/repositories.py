from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from dragonboat_ai.futures_agent.domain.market_data import (
    ContractCandidate,
    ContractRef,
    ContinuousBar,
    CurveSnapshot,
    DailyBar,
    InstrumentRef,
)
from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis


class MarketDataRepository(Protocol):
    def resolve_instrument(
        self,
        *,
        symbol: str,
        exchange: str | None = None,
    ) -> InstrumentRef:
        ...

    def resolve_contract(
        self,
        *,
        symbol: str,
        contract_code: str,
        exchange: str | None = None,
    ) -> ContractRef:
        ...

    def load_contract_bars(
        self,
        *,
        contract_id: int,
        as_of: datetime,
        limit: int,
    ) -> tuple[DailyBar, ...]:
        ...

    def load_continuous_bars(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
        limit: int,
        calculation_version: str,
    ) -> tuple[ContinuousBar, ...]:
        ...

    def load_curve_snapshots(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
        limit: int,
    ) -> tuple[CurveSnapshot, ...]:
        ...

    def candidates_from_curve(
        self,
        snapshot: CurveSnapshot,
    ) -> list[ContractCandidate]:
        ...

    def latest_roll_date(
        self,
        *,
        instrument_id: int,
        as_of: datetime,
    ) -> date | None:
        ...


class AnalysisRepository(Protocol):
    def find_cached(
        self,
        *,
        request_hash: str,
        input_data_hash: str,
        version_hash: str,
    ) -> FuturesMarketAnalysis | None:
        ...

    def get(self, analysis_id: str) -> FuturesMarketAnalysis | None:
        ...

    def latest(self, symbol: str, horizon: str) -> FuturesMarketAnalysis | None:
        ...

    def save(
        self,
        analysis: FuturesMarketAnalysis,
        *,
        version_hash: str,
    ) -> FuturesMarketAnalysis:
        ...
