from __future__ import annotations

from dragonboat_ai.futures_agent.domain.enums import AnalysisHorizon, DataStatus
from dragonboat_ai.futures_agent.domain.market_data import MarketContext
from dragonboat_ai.futures_agent.domain.models import DataQualityAssessment
from dragonboat_ai.futures_agent.features.normalization import clip


class DataQualityEvaluator:
    """Evaluate whether deterministic analysis can proceed without guessing."""

    def assess(self, context: MarketContext) -> DataQualityAssessment:
        continuous_required = 61 if context.request.horizon is AnalysisHorizon.SWING else 121
        contract_required = 21

        continuous_score = clip(len(context.continuous_bars) / continuous_required * 100.0, 0.0, 100.0)
        contract_score = clip(len(context.contract_bars) / contract_required * 100.0, 0.0, 100.0)
        curve_score = 100.0 if context.current_curve and len(context.current_curve.points) >= 2 else 0.0
        metadata_score = 100.0 if context.days_to_expiry >= 0 else 0.0
        coverage = (
            0.40 * continuous_score
            + 0.25 * contract_score
            + 0.20 * curve_score
            + 0.15 * metadata_score
        )

        blocking: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []
        stale: list[str] = []

        if len(context.continuous_bars) < 21:
            blocking.append("continuous_series_has_fewer_than_21_bars")
        elif len(context.continuous_bars) < continuous_required:
            warnings.append("continuous_series_history_is_short_for_selected_horizon")

        if len(context.contract_bars) < 6:
            blocking.append("selected_contract_has_fewer_than_6_bars")
        elif len(context.contract_bars) < contract_required:
            warnings.append("selected_contract_history_is_short")

        if context.current_curve is None or len(context.current_curve.points) < 2:
            missing.append("term_structure_curve")
            warnings.append("term_structure_factor_will_be_missing")

        future_timestamps = [
            item.available_at
            for item in (*context.contract_bars, *context.continuous_bars)
            if item.available_at > context.request.as_of
        ]
        if context.current_curve and context.current_curve.available_at > context.request.as_of:
            future_timestamps.append(context.current_curve.available_at)
        if future_timestamps:
            blocking.append("market_context_contains_data_not_available_at_as_of")

        dependencies = {
            "continuous_series": context.continuous_bars,
            "selected_contract": context.contract_bars,
            "term_structure_curve": (context.current_curve,) if context.current_curve else (),
        }
        for source, observations in dependencies.items():
            if not observations:
                continue
            # Check each dependency independently; a new correction does not make
            # an old trading session fresh. The 7-day bound is conservative for
            # this daily research service, not a production exchange calendar SLA.
            latest = max(observations, key=lambda item: item.trading_date)
            age = (context.request.as_of.date() - latest.trading_date).days
            if age > 7:
                stale.append(source)
                blocking.append(f"stale_{source}")
        if not context.contract_bars and not context.continuous_bars:
            blocking.append("no_daily_market_data")

        overall = coverage
        if stale:
            overall -= 15.0
        if blocking:
            overall = min(overall, 40.0)
        overall = clip(overall, 0.0, 100.0)

        if blocking or overall < 60.0:
            status = DataStatus.INSUFFICIENT
        elif overall < 85.0 or missing or warnings:
            status = DataStatus.PARTIAL
        else:
            status = DataStatus.OK

        return DataQualityAssessment(
            status=status,
            overall_score=overall,
            required_data_coverage=coverage,
            stale_sources=stale,
            missing_fields=missing,
            blocking_issues=blocking,
            warnings=warnings,
        )
