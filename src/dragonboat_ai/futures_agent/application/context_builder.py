from __future__ import annotations

import hashlib
import json

from dragonboat_ai.futures_agent.contracts.main_contract_policy import (
    LiquidityConfirmedMainContractPolicy,
)
from dragonboat_ai.futures_agent.domain.exceptions import InsufficientDataError
from dragonboat_ai.futures_agent.domain.market_data import MarketContext
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.ports.repositories import MarketDataRepository
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig


class SqlAlchemyMarketContextBuilder:
    def __init__(
        self,
        repository: MarketDataRepository,
        *,
        config: ScoringConfig | None = None,
        continuous_calculation_version: str = "continuous_v1",
    ) -> None:
        self.repository = repository
        self.config = config or ScoringConfig.default()
        main = self.config.main_contract
        self.policy = LiquidityConfirmedMainContractPolicy(
            exclude_days_to_expiry_below=int(main["exclude_days_to_expiry_below"]),
            confirmation_days=int(main["confirmation_days"]),
            minimum_volume_share=main["minimum_volume_share"],
            minimum_oi_share=main["minimum_oi_share"],
        )
        self.continuous_calculation_version = continuous_calculation_version

    def build(self, request: AnalysisRequest) -> MarketContext:
        instrument = self.repository.resolve_instrument(
            symbol=request.symbol,
            exchange=request.exchange,
        )
        curves = self.repository.load_curve_snapshots(
            instrument_id=instrument.instrument_id,
            as_of=request.as_of,
            limit=400,
        )
        current_curve = curves[-1] if curves else None

        if request.contract:
            selected = self.repository.resolve_contract(
                symbol=request.symbol,
                contract_code=request.contract,
                exchange=request.exchange,
            )
            selection_reason = "explicit_contract_request"
        else:
            if not curves:
                raise InsufficientDataError(
                    "Main-contract selection requires at least one visible curve snapshot."
                )
            history_length = max(int(self.config.main_contract["confirmation_days"]), 2)
            candidate_history = [
                self.repository.candidates_from_curve(snapshot)
                for snapshot in reversed(curves[-history_length:])
            ]
            selection = self.policy.select(candidate_history)
            selected = selection.selected.contract
            selection_reason = selection.reason

        contract_bars = self.repository.load_contract_bars(
            contract_id=selected.contract_id,
            as_of=request.as_of,
            limit=500,
        )
        continuous_bars = self.repository.load_continuous_bars(
            instrument_id=selected.instrument_id,
            as_of=request.as_of,
            limit=600,
            calculation_version=self.continuous_calculation_version,
        )
        days_to_expiry = (selected.expiry_date - request.as_of.date()).days
        recent_roll_date = self.repository.latest_roll_date(
            instrument_id=selected.instrument_id,
            as_of=request.as_of,
        )
        input_hash = self._input_hash(
            request=request,
            selected_contract=selected.contract_code,
            contract_bars=contract_bars,
            continuous_bars=continuous_bars,
            curves=curves,
        )
        return MarketContext(
            request=request,
            instrument_id=selected.instrument_id,
            contract_id=selected.contract_id,
            exchange=selected.exchange,
            symbol=selected.symbol,
            selected_contract=selected.contract_code,
            contract_bars=contract_bars,
            continuous_bars=continuous_bars,
            current_curve=current_curve,
            historical_curves=curves,
            days_to_expiry=days_to_expiry,
            recent_roll_date=recent_roll_date,
            contract_selection_reason=selection_reason,
            input_data_hash=input_hash,
        )

    @staticmethod
    def _input_hash(
        *,
        request: AnalysisRequest,
        selected_contract: str,
        contract_bars,
        continuous_bars,
        curves,
    ) -> str:
        payload = {
            "request": request.model_dump(
                mode="json",
                exclude={"include_narrative", "force_refresh"},
            ),
            "selected_contract": selected_contract,
            "contract_bars": [
                [bar.contract, bar.trading_date.isoformat(), bar.revision_no, bar.payload_hash]
                for bar in contract_bars
            ],
            "continuous_bars": [
                [bar.source_contract, bar.trading_date.isoformat(), bar.input_hash]
                for bar in continuous_bars
            ],
            "curves": [
                [curve.snapshot_id, curve.trading_date.isoformat(), curve.input_hash]
                for curve in curves
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
