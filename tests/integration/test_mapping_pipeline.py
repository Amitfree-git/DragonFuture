from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.contracts.mapping_pipeline import build_mapping_and_continuous
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
from tests.integration.test_tushare_ingest import _source

SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.mark.integration
def test_mapping_pipeline_persists_effective_main_and_continuous(database) -> None:
    repo = database["market_repository"]
    TushareMarketIngestor(repo, _source()).ingest(
        product="RB",
        exchange="SHFE",
        start="20260901",
        end="20260902",
    )
    as_of = datetime(2026, 9, 2, 16, 0, tzinfo=SHANGHAI)
    report = build_mapping_and_continuous(repo, symbol="RB", exchange="SHFE", as_of=as_of)
    assert report.mappings == 2
    assert report.continuous_bars == 2
    context = SqlAlchemyMarketContextBuilder(repo).build(
        AnalysisRequest(symbol="RB", exchange="SHFE", as_of=as_of, include_narrative=False)
    )
    assert context.contract_selection_reason == "effective_session_mapping"
    assert context.selected_contract in {"RB2610", "RB2701", "RB2705"}
    assert context.continuous_bars
