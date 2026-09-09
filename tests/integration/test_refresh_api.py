from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from dragonboat_ai.futures_agent.api.app import create_app


def test_refresh_route_invokes_coordinator_and_preserves_result(tmp_path):
    app = create_app(f'sqlite:///{tmp_path}/api.db')
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        return {'refresh': {'status': 'up_to_date', 'latest_session': '2026-09-04'},
                'analysis': {'opportunity': {'action': 'no_trade'}, 'risk': {'hard_gate_triggered': True}}}
    app.state.refresh_service = SimpleNamespace(run=run)
    with TestClient(app) as client:
        response = client.post('/api/v1/futures/refresh_and_analyze', json={'symbol':'rb','exchange':'shfe','horizon':'position'})
    assert response.status_code == 200
    assert calls == [{'symbol':'RB','exchange':'SHFE','horizon':'position'}]
    assert response.json()['analysis']['risk']['hard_gate_triggered'] is True
    assert response.json()['refresh']['latest_session'] == '2026-09-04'


@pytest.mark.parametrize('extra', [{'as_of':'2026-09-04T16:00:00+08:00'}, {'horizon':'intraday'}, {'exchange':'unknown'}, {'symbol':'../x'}, {'token':'must-not-be-accepted'}])
def test_refresh_request_rejects_unsupported_options(tmp_path, extra):
    app = create_app(f'sqlite:///{tmp_path}/api.db')
    with TestClient(app) as client:
        response = client.post('/api/v1/futures/refresh_and_analyze', json={'symbol':'RB','exchange':'SHFE',**extra})
    assert response.status_code == 422


def test_refresh_error_exposes_sanitized_code_without_old_analysis(tmp_path):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    app = create_app(f'sqlite:///{tmp_path}/api.db')
    def run(**kwargs):raise RefreshError('source_unavailable')
    app.state.refresh_service = SimpleNamespace(run=run)
    with TestClient(app) as client:
        response=client.post('/api/v1/futures/refresh_and_analyze',json={'symbol':'RB','exchange':'SHFE'})
    assert response.status_code==503
    assert response.json()['detail']=={'status':'refresh_failed','code':'source_unavailable','consumer_intent':'blocked'}
    assert 'analysis' not in response.json()


def test_refresh_honors_existing_api_auth(tmp_path,monkeypatch):
    monkeypatch.setenv('DRAGONBOAT_FUTURES_API_TOKEN','test-only-token')
    app=create_app(f'sqlite:///{tmp_path}/api.db')
    def forbidden(**kwargs):raise AssertionError('unauthorized request must not fetch data')
    app.state.refresh_service=SimpleNamespace(run=forbidden)
    with TestClient(app) as client:
        response=client.post('/api/v1/futures/refresh_and_analyze',json={'symbol':'RB','exchange':'SHFE'})
    assert response.status_code==401
