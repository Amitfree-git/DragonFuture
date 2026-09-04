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

        latest = client.get("/api/v1/futures/symbols/RB/latest?horizon=swing")
        assert latest.status_code == 200
        assert latest.json()["analysis_id"] == body["analysis_id"]


@pytest.mark.integration
def test_missing_analysis_returns_404(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'api-404.db'}")
    with TestClient(app) as client:
        response = client.get("/api/v1/futures/analyses/not-found")
    assert response.status_code == 404
