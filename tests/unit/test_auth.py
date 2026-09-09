import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from dragonboat_ai.futures_agent.api.app import create_app
from dragonboat_ai.futures_agent.operations.auth import ReadOnlyAccessMiddleware, redact
from tests.support import seed_reference_market


def test_redact_strips_bearer_and_tushare_token() -> None:
    text = "Authorization: Bearer super-secret-token TUSHARE_TOKEN=abc123"
    cleaned = redact(text)
    assert "super-secret-token" not in cleaned
    assert "abc123" not in cleaned
    assert "Bearer ***" in cleaned
    assert "TUSHARE_TOKEN=***" in cleaned


@pytest.mark.integration
def test_unauthorized_without_bearer_when_token_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DRAGONBOAT_FUTURES_API_TOKEN", "expected-token")
    app = create_app(f"sqlite:///{tmp_path / 'auth.db'}")
    fixture = seed_reference_market(app.state.market_repository)
    payload = {
        "symbol": "RB",
        "exchange": "SHFE",
        "horizon": "swing",
        "as_of": fixture["as_of"].isoformat(),
        "include_narrative": False,
    }
    with TestClient(app) as client:
        public = client.get("/api/v1/futures/health")
        assert public.status_code == 200
        denied = client.post("/api/v1/futures/analyses", json=payload)
        assert denied.status_code == 401
        allowed = client.post(
            "/api/v1/futures/analyses",
            json=payload,
            headers={"Authorization": "Bearer expected-token"},
        )
        assert allowed.status_code == 200


def test_rate_limit_returns_429(monkeypatch) -> None:
    monkeypatch.delenv("DRAGONBOAT_FUTURES_API_TOKEN", raising=False)
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/private", ok)])
    app.add_middleware(ReadOnlyAccessMiddleware, max_per_minute=1)
    with TestClient(app) as client:
        first = client.get("/private")
        second = client.get("/private")
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.integration
def test_optional_auth_does_not_break_existing_clients(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DRAGONBOAT_FUTURES_API_TOKEN", raising=False)
    app = create_app(f"sqlite:///{tmp_path / 'optional-auth.db'}")
    with TestClient(app) as client:
        response = client.get("/api/v1/futures/ready")
    # Authentication remains optional; an empty DB correctly fails readiness.
    assert response.status_code == 503
