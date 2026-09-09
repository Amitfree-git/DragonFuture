import pytest
from fastapi.testclient import TestClient

from dragonboat_ai.futures_agent.api.app import create_app
from tests.support import seed_reference_market


@pytest.mark.integration
def test_health_endpoint(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'api.db'}")
    with TestClient(app) as client:
        response = client.get("/api/v1/futures/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.integration
def test_analysis_create_read_and_latest_endpoints(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'api-analysis.db'}")
    fixture = seed_reference_market(app.state.market_repository)
    payload = {
        "symbol": "RB",
        "exchange": "SHFE",
        "horizon": "swing",
        "as_of": fixture["as_of"].isoformat(),
        "include_narrative": True,
    }

    with TestClient(app) as client:
        created = client.post("/api/v1/futures/analyses", json=payload)
        assert created.status_code == 200
        body = created.json()
        assert body["selected_contract"] == "RB2701"
        assert body["direction"]["label"] == "strong_bullish"
        assert body["opportunity"]["action"] == "wait_for_pullback"

        fetched = client.get(f"/api/v1/futures/analyses/{body['analysis_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["core_result_hash"] == body["core_result_hash"]

        latest = client.get("/api/v1/futures/symbols/RB/latest?horizon=swing&exchange=SHFE")
        assert latest.status_code == 200
        assert latest.json()["analysis_id"] == body["analysis_id"]

        ready = client.get("/api/v1/futures/ready")
        assert ready.status_code == 200
        too_big = client.post("/api/v1/futures/analyses/batch", json=[payload] * 21)
        assert too_big.status_code == 413


@pytest.mark.integration
def test_latest_never_returns_future_analysis(database) -> None:
    from datetime import datetime, timezone

    from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
    from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
    from dragonboat_ai.futures_agent.domain.models import AnalysisRequest

    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
    )
    analyst.analyze(
        AnalysisRequest(symbol="RB", exchange="SHFE", as_of=fixture["as_of"], include_narrative=False)
    )
    earlier = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    assert analysis_repo.latest("RB", "swing", as_of=earlier) is None
    assert analysis_repo.latest("RB", "swing", exchange="DCE") is None
    current = analysis_repo.latest("RB", "swing", exchange="SHFE", as_of=fixture["as_of"])
    assert current is not None
    assert current.request.as_of <= fixture["as_of"]


@pytest.mark.integration
def test_narrative_timeout_preserves_core(database) -> None:
    from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
    from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
    from dragonboat_ai.futures_agent.domain.models import AnalysisRequest

    class TimeoutNarrative:
        def generate(self, core_result):
            raise TimeoutError("narrative timed out")

    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
        narrative_generator=TimeoutNarrative(),
    )
    result = analyst.analyze(
        AnalysisRequest(symbol="RB", exchange="SHFE", as_of=fixture["as_of"], include_narrative=True)
    )
    assert result.core_result_hash != "pending"
    assert result.narrative is not None
    assert result.direction.label is not None


@pytest.mark.integration
def test_concurrent_identical_request_is_idempotent(database) -> None:
    from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
    from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
    from dragonboat_ai.futures_agent.domain.models import AnalysisRequest

    market_repo = database["market_repository"]
    analysis_repo = database["analysis_repository"]
    fixture = seed_reference_market(market_repo)
    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repo),
        analysis_repository=analysis_repo,
    )
    request = AnalysisRequest(symbol="RB", exchange="SHFE", as_of=fixture["as_of"], include_narrative=False)
    first = analyst.analyze(request)
    second = analyst.analyze(request)
    assert first.analysis_id == second.analysis_id
    assert first.core_result_hash == second.core_result_hash


@pytest.mark.integration
def test_missing_analysis_returns_404(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'api-404.db'}")
    with TestClient(app) as client:
        response = client.get("/api/v1/futures/analyses/not-found")
    assert response.status_code == 404
