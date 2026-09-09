import json
from fastapi.testclient import TestClient
from dragonboat_ai.futures_agent.api.app import create_app
from tests.support import seed_reference_market


def test_bot_catalog_exposes_data_coverage_and_version(tmp_path):
    app=create_app(f'sqlite:///{tmp_path}/bot.db')
    fixture=seed_reference_market(app.state.market_repository)
    with TestClient(app) as client:
        response=client.get('/api/v1/futures/catalog')
        assert response.status_code==200
        body=response.json()
        assert body['production_ready'] is False
        assert body['code_artifact'].startswith('sha256:')
        assert body['instruments'][0]['symbol']=='RB'


def test_bot_summary_preserves_hard_gate():
    from dragonboat_ai.futures_agent.operations.bot_reader import summarize
    payload={'analysis_id':'x','selected_contract':'RB2701','request':{'symbol':'RB','exchange':'SHFE','as_of':'2026-09-04T08:00:00Z'},'data_mode':'final_only','production_ready':False,'versions':{'code_commit':'sha256:verified'},'direction':{'score':90},'risk':{'hard_gate_triggered':True,'items':[]},'opportunity':{'action':'no_trade','hard_gate_reasons':['missing_limits']},'data_quality':{'status':'ok'}}
    result=summarize(payload)
    assert result['opportunity']['action']=='no_trade'
    assert result['consumer_intent']=='blocked'
    assert result['data_mode']=='final_only'
    assert result['production_ready'] is False
