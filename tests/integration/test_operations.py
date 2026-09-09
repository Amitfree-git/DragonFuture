import pytest

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.infrastructure.database.session import create_sqlite_engine
from dragonboat_ai.futures_agent.operations.backup import (
    backup_sqlite,
    canonical_row_hash,
    restore_sqlite,
    table_count,
)
from dragonboat_ai.futures_agent.operations.probe import measure_analysis_latency
from dragonboat_ai.futures_agent.operations.shadow import SqlShadowStore, ShadowRunner
from dragonboat_ai.futures_agent.operations.watermark import SHANGHAI
from tests.support import seed_reference_market


@pytest.mark.integration
def test_backup_restore_preserves_row_count_and_hash(database, tmp_path) -> None:
    fixture = seed_reference_market(database["market_repository"])
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(database["market_repository"]),
        analysis_repository=database["analysis_repository"],
    )
    analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            include_narrative=False,
        )
    )
    database["engine"].dispose()

    source_url = database["url"]
    columns = ("analysis_id", "core_result_hash")
    source_count = table_count(source_url, "fut_analysis_run")
    source_hash = canonical_row_hash(source_url, "fut_analysis_run", columns)
    assert source_count == 1

    backup_path = backup_sqlite(source_url, tmp_path / "backup.db")
    restore_url = f"sqlite:///{tmp_path / 'restored.db'}"
    restore_sqlite(backup_path, restore_url)

    assert table_count(restore_url, "fut_analysis_run") == source_count
    assert canonical_row_hash(restore_url, "fut_analysis_run", columns) == source_hash
    assert table_count(restore_url, "fut_event_outbox") == 1


@pytest.mark.integration
def test_sqlite_engine_rejects_non_sqlite_urls() -> None:
    with pytest.raises(ValueError, match="SQLite"):
        create_sqlite_engine("postgresql://localhost/futures")


@pytest.mark.integration
def test_probe_records_real_milliseconds(database) -> None:
    fixture = seed_reference_market(database["market_repository"])
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(database["market_repository"]),
        analysis_repository=database["analysis_repository"],
    )
    request = AnalysisRequest(
        symbol="RB",
        exchange="SHFE",
        as_of=fixture["as_of"],
        include_narrative=False,
    )
    report = measure_analysis_latency(analyst, request, samples=2)
    assert report.samples == 2
    assert report.mean_ms > 0
    assert report.max_ms >= report.mean_ms
    assert "Not a production SLO" in report.notes


@pytest.mark.integration
def test_shadow_store_persists_gaps(database) -> None:
    from datetime import date, datetime

    store = SqlShadowStore(database["session_factory"])
    runner = ShadowRunner(store=store)
    observation = runner.run_session(
        exchange="SHFE",
        symbol="RB",
        session_date=date(2026, 9, 4),
        now=datetime(2026, 9, 4, 14, 0, tzinfo=SHANGHAI),
        settlement_available_at=None,
        analyze=lambda: None,
    )
    assert observation.gap is True
    assert table_count(database["url"], "fut_shadow_run") == 1
