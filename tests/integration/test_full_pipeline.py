from dataclasses import replace

import pytest
from sqlalchemy import func, select

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.domain.exceptions import NarrativeValidationError
from dragonboat_ai.futures_agent.narrative.llm_adapter import LLMNarrativeGenerator
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig
from dragonboat_ai.futures_agent.infrastructure.database.models import (
    FutFactorSnapshotORM,
    FutFeatureSnapshotORM,
    FutFeatureValueORM,
)

from tests.support import seed_reference_market


class UngroundedNarrativeClient:
    def complete_json(self, *, system_prompt, payload):
        return {
            "executive_summary": "未引用证据的摘要。",
            "market_structure": "结构说明。",
            "bullish_case": ["这是一个没有证据编号的多头判断。"],
            "bearish_case": [],
            "conflict_analysis": [],
            "risk_summary": [],
            "invalidation_summary": [],
            "final_conclusion": "结论。",
        }


@pytest.mark.integration
def test_full_pipeline_persists_and_reloads_analysis(database) -> None:
    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
    )
    request = AnalysisRequest(
        symbol="RB",
        exchange="SHFE",
        as_of=fixture["as_of"],
        horizon="swing",
        include_narrative=True,
    )
    result = analyst.analyze(request)

    assert result.selected_contract == "RB2701"
    assert result.direction.score is not None
    assert result.direction.score > 0
    assert result.core_result_hash != "pending"
    assert result.narrative is not None
    assert all(
        "evidence_id=" in item
        for item in result.narrative.bullish_case + result.narrative.bearish_case
    )
    assert result.input_data_hash
    assert len(result.metrics) >= 20
    assert result.metrics["curve_slope"].value > 0
    assert result.metrics["curve_slope"].normalized_score > 0

    restored = analysis_repo.get(result.analysis_id)
    assert restored is not None
    assert restored.core_result_hash == result.core_result_hash
    assert restored.narrative == result.narrative

    with database["session_factory"]() as session:
        assert session.scalar(select(func.count()).select_from(FutFeatureSnapshotORM)) == 1
        assert session.scalar(select(func.count()).select_from(FutFeatureValueORM)) == len(
            result.metrics
        )
        assert session.scalar(select(func.count()).select_from(FutFactorSnapshotORM)) == len(
            result.factors
        )

    cached = analyst.analyze(request)
    assert cached.analysis_id == result.analysis_id


@pytest.mark.integration
def test_cache_identity_includes_narrative_request_and_model_versions(database) -> None:
    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)

    base_analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
    )
    no_narrative = base_analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            horizon="swing",
            include_narrative=False,
        )
    )
    with_narrative = base_analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            horizon="swing",
            include_narrative=True,
        )
    )

    assert no_narrative.narrative is None
    assert with_narrative.narrative is not None
    assert with_narrative.analysis_id != no_narrative.analysis_id

    changed_versions = base_analyst.versions.model_copy(
        update={"factor_model_version": "futures_factors_v1.1-test"}
    )
    upgraded_analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
        versions=changed_versions,
    )
    upgraded = upgraded_analyst.analyze(with_narrative.request)

    assert upgraded.analysis_id != with_narrative.analysis_id
    assert upgraded.versions.factor_model_version == "futures_factors_v1.1-test"
    assert upgraded.core_result_hash != with_narrative.core_result_hash

    reference_config = ScoringConfig.default()
    custom_weights = {
        **reference_config.direction_weights,
        "swing": {
            "trend": 0.35,
            "momentum": 0.30,
            "positioning": 0.15,
            "term_structure": 0.20,
        },
    }
    custom_config = replace(reference_config, direction_weights=custom_weights)
    custom_versions = base_analyst.versions.model_copy(
        update={"score_config_hash": ""}
    )
    custom_analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo, config=custom_config),
        analysis_repository=analysis_repo,
        config=custom_config,
        versions=custom_versions,
    )
    custom = custom_analyst.analyze(with_narrative.request)

    assert custom.analysis_id != with_narrative.analysis_id
    assert custom.versions.score_config_hash == custom_config.fingerprint()
    assert custom.direction.score != with_narrative.direction.score


@pytest.mark.integration
def test_ungrounded_llm_narrative_is_rejected_and_falls_back(database) -> None:
    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    context_builder = SqlAlchemyMarketContextBuilder(market_repo)

    core = FuturesMarketAnalyst(
        context_builder=context_builder,
        analysis_repository=analysis_repo,
    ).analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            horizon="swing",
            include_narrative=False,
        )
    )
    generator = LLMNarrativeGenerator(UngroundedNarrativeClient())
    with pytest.raises(NarrativeValidationError, match="missing an evidence_id"):
        generator.generate(core)

    result = FuturesMarketAnalyst(
        context_builder=context_builder,
        analysis_repository=analysis_repo,
        narrative_generator=generator,
    ).analyze(
        core.request.model_copy(update={"include_narrative": True})
    )
    assert result.narrative is not None
    assert result.narrative.executive_summary.startswith("RB/RB2701")
    assert all(
        "evidence_id=" in item
        for item in result.narrative.bullish_case + result.narrative.bearish_case
    )
