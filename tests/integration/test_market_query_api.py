from fastapi.testclient import TestClient
from dragonboat_ai.futures_agent.api.app import create_app
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_queries import McpMarketQueries
from tests.unit.test_mcp_market_queries import Transport,stock


def test_stock_endpoint_preserves_contract_and_closes(database):
    app=create_app(database['url']);t=Transport(stock())
    app.state.market_query_factory=lambda:McpMarketQueries(transport=t)
    with TestClient(app) as client:
        r=client.post('/api/v1/market-data/price_history',json={'asset_type':'hk_stock','code':'00700.HK','start':'2026-09-01','end':'2026-09-04'})
    assert r.status_code==200
    assert r.json()['data']['source']=='yahoo'
    assert r.json()['data']['currency']=='HKD'
    assert t.closed


def test_stock_endpoint_rejects_wrong_market_and_adjustment(database):
    app=create_app(database['url'])
    with TestClient(app) as client:
        for extra in [{'asset_type':'futures'},{'adjust':'qfq'},{'start':'2026-02-30'}]:
            r=client.post('/api/v1/market-data/price_history',json={'asset_type':'us_stock','code':'AAPL','start':'20260901','end':'20260904',**extra})
            assert r.status_code==422


def test_provider_failure_closes_and_sanitizes(database):
    app=create_app(database['url']);t=Transport(stock());t.call_tool=lambda *a:{'isError':True,'content':[{'type':'text','text':'SECRET'}]}
    app.state.market_query_factory=lambda:McpMarketQueries(transport=t)
    with TestClient(app) as client:
        r=client.post('/api/v1/market-data/price_history',json={'asset_type':'us_stock','code':'AAPL','start':'20260901','end':'20260904'})
    assert r.status_code==503 and 'SECRET' not in r.text and t.closed

def test_incomplete_mapping_and_roll_contracts_survive_api(database):
    app=create_app(database['url'])
    for endpoint,collection in [('futures_main_mapping_history','records'),('futures_roll_events','events')]:
        data={'source':'tushare','product':'M','exchange':'DCE','complete':False,'completeness':'incomplete',collection:[],'point_in_time_verified':False}
        t=Transport(data);app.state.market_query_factory=lambda:McpMarketQueries(transport=t)
        with TestClient(app) as client:
            r=client.post('/api/v1/market-data/'+endpoint,json={'product':'M','exchange':'DCE','start':'20260901','end':'20260904'})
        assert r.status_code==200 and r.json()['data']['complete'] is False
        assert r.json()['data']['point_in_time_verified'] is False and t.closed


def test_disabled_provider_is_distinguishable(database):
    import json
    app=create_app(database['url']);t=Transport(stock())
    t.call_tool=lambda *a:{'content':[{'type':'text','text':json.dumps({'ok':False,'code':'NO_ENABLED_PROVIDER','message':'private-upstream-message'})}]}
    app.state.market_query_factory=lambda:McpMarketQueries(transport=t)
    with TestClient(app) as client:
        r=client.post('/api/v1/market-data/price_history',json={'asset_type':'us_stock','code':'AAPL','start':'20260901','end':'20260904'})
    assert r.status_code==503 and r.json()['detail']['code']=='NO_ENABLED_PROVIDER'
    assert 'private-upstream-message' not in r.text and t.closed
