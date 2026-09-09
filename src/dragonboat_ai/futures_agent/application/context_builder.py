from __future__ import annotations

import hashlib
import json

from dragonboat_ai.futures_agent.contracts.main_contract_state import MainContractStateMachine, MappingAction
from dragonboat_ai.futures_agent.contracts.main_contract_policy import (
    LiquidityConfirmedMainContractPolicy,
)
from dragonboat_ai.futures_agent.domain.eligibility import days_to_tradable_end
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
        snapshot_reader = getattr(self.repository, "read_snapshot", None)
        if snapshot_reader is None:
            return self._build(request)
        with snapshot_reader() as repository:
            builder = type(self)(repository, config=self.config,
                                 continuous_calculation_version=self.continuous_calculation_version)
            return builder._build(request)

    def _build(self, request: AnalysisRequest) -> MarketContext:
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
        if len({curve.source for curve in curves}) > 1:
            raise InsufficientDataError("Mixed curve sources cannot form one research context.")

        validator = getattr(self.repository, "validate_series_inputs", None)
        if validator is not None:
            validator(instrument_id=instrument.instrument_id, as_of=request.as_of, curves=curves,
                      calculation_version=self.continuous_calculation_version)

        if request.contract:
            selected = self.repository.resolve_contract(
                symbol=request.symbol,
                contract_code=request.contract,
                exchange=request.exchange,
            )
            selection_reason = "explicit_contract_request"
            series_basis = "selected_contract"
            mapping_effective_session = None
        else:
            mapping = self.repository.load_effective_mapping(
                instrument_id=instrument.instrument_id,
                session_date=request.as_of.date(),
                as_of=request.as_of,
            )
            if mapping is not None:
                if mapping.action == "blocked" or mapping.contract is None:
                    raise InsufficientDataError("Main-contract mapping is blocked for this session.")
                selected = mapping.contract
                selection_reason = "effective_session_mapping"
                series_basis = "continuous"
                mapping_effective_session = mapping.effective_session
            else:
                if not curves:
                    raise InsufficientDataError(
                        "Main-contract selection requires at least one visible curve snapshot."
                    )
                records = MainContractStateMachine(self.policy).replay([
                    (snapshot.trading_date, self.repository.candidates_from_curve(snapshot))
                    for snapshot in curves
                ])
                last = records[-1]
                code = last.effective_contract
                if (last.action is MappingAction.CONFIRMED_ROLL and last.effective_session is not None
                        and last.effective_session <= request.as_of.date()):
                    code = last.decision_contract
                if code is None or last.action is MappingAction.BLOCKED:
                    raise InsufficientDataError("Main-contract mapping is blocked for this session.")
                selected = self.repository.resolve_contract(symbol=request.symbol, contract_code=code,
                                                            exchange=request.exchange)
                selection_reason = "replayed_main_contract_mapping"
                series_basis = "continuous"
                mapping_effective_session = last.effective_session

        contract_bars = self.repository.load_contract_bars(
            contract_id=selected.contract_id,
            as_of=request.as_of,
            limit=500,
            source=current_curve.source if current_curve else None,
        )
        continuous_bars = self.repository.load_continuous_bars(
            instrument_id=selected.instrument_id,
            as_of=request.as_of,
            limit=600,
            calculation_version=self.continuous_calculation_version,
        )
        days_to_expiry = days_to_tradable_end(selected, request.as_of.date())
        recent_roll_date = self.repository.latest_roll_date(
            instrument_id=selected.instrument_id,
            as_of=request.as_of,
        )
        input_hash = self._input_hash(
            request=request,
            selected=selected,
            contract_bars=contract_bars,
            continuous_bars=continuous_bars,
            curves=curves,
            mapping_identity=(selection_reason, mapping_effective_session.isoformat() if mapping_effective_session else None),
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
            series_basis=series_basis,
            mapping_effective_session=mapping_effective_session,
            series_snapshot_id=continuous_bars[-1].series_snapshot_id if continuous_bars else None,
            data_mode=("captured_revisions" if contract_bars and continuous_bars
                       and all(b.data_mode == "captured_revisions" for b in (*contract_bars, *continuous_bars))
                       else "final_only"),
        )

    @staticmethod
    def _input_hash(
        *,
        request: AnalysisRequest,
        selected,
        contract_bars,
        continuous_bars,
        curves,
        mapping_identity=None,
    ) -> str:
        payload = {
            "request": request.model_dump(
                mode="json",
                exclude={"include_narrative", "force_refresh"},
            ),
            "selected_contract": selected.contract_code,
            "mapping_identity": mapping_identity,
            "contract_spec": {
                "last_trade_date": selected.last_trade_date.isoformat() if selected.last_trade_date else None,
                "expiry_date": selected.expiry_date.isoformat(),
                "tradable_until": selected.tradable_until.isoformat() if selected.tradable_until else None,
            },
            "contract_bars": [
                [bar.contract, bar.trading_date.isoformat(), bar.revision_no, bar.payload_hash]
                for bar in contract_bars
            ],
            "continuous_bars": [
                [bar.source_contract, bar.trading_date.isoformat(), bar.input_hash, bar.series_snapshot_id, str(bar.research_index)]
                for bar in continuous_bars
            ],
            "curves": [
                [curve.snapshot_id, curve.trading_date.isoformat(), curve.input_hash]
                for curve in curves
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()
