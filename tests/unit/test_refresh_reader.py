import json
import sys
from types import SimpleNamespace

import pytest
from dragonboat_ai.futures_agent.operations import bot_reader


def test_refresh_client_posts_only_fixed_analysis_operation(monkeypatch):
    captured=[]
    class Response:
        url='http://127.0.0.1:8000/api/v1/futures/refresh_and_analyze'
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'{"refresh":{"status":"updated"}}'
    def open_request(request,timeout):
        captured.append((request,timeout));return Response()
    monkeypatch.setattr(bot_reader,'build_opener',lambda *args:SimpleNamespace(open=open_request))
    result=bot_reader.read_json('http://127.0.0.1:8000','/refresh_and_analyze',payload={'symbol':'RB','exchange':'SHFE','horizon':'swing'})
    request,timeout=captured[0]
    assert request.get_method()=='POST'
    assert json.loads(request.data)['symbol']=='RB'
    assert timeout==180
    assert result['refresh']['status']=='updated'
    with pytest.raises(ValueError):
        bot_reader.read_json('http://example.com','/refresh_and_analyze',payload={})
    with pytest.raises(ValueError):
        bot_reader.read_json('http://127.0.0.1:8000','/other',payload={})


def test_refresh_cli_keeps_actual_data_date_and_risk_block(monkeypatch,capsys):
    payload={'analysis_id':'x','request':{'as_of':'2026-09-05T08:00:00Z'},'risk':{'hard_gate_triggered':True},'opportunity':{'action':'no_trade'},'data_mode':'final_only','versions':{'code_commit':'sha256:test'}}
    def request(base,path,**kwargs):
        if path=='/catalog':return {'code_artifact':'sha256:test'}
        assert kwargs['payload']=={'symbol':'RB','exchange':'SHFE','horizon':'swing'}
        return {'refresh':{'status':'up_to_date','latest_session':'2026-09-04'},'analysis':payload}
    monkeypatch.setattr(bot_reader,'read_json',request)
    monkeypatch.setattr(sys,'argv',['grok_query.py','refresh_and_analyze'])
    bot_reader.main()
    result=json.loads(capsys.readouterr().out)
    assert result['refresh']['latest_session']=='2026-09-04'
    assert result['analysis']['consumer_intent']=='blocked'


def test_refresh_cli_rejects_historical_cutoff(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['grok_query.py','refresh_and_analyze','--as-of','2026-01-01T00:00:00Z'])
    with pytest.raises(SystemExit) as exc:bot_reader.main()
    assert exc.value.code==1
    assert json.loads(capsys.readouterr().out)['consumer_intent']=='blocked'


def test_refresh_cli_explains_server_failure(monkeypatch,capsys):
    from io import BytesIO
    from urllib.error import HTTPError
    def failed(*args,**kwargs):
        raise HTTPError('http://127.0.0.1:8000',503,'Unavailable',{},BytesIO(b'{"detail":{"code":"missing_target_data"}}'))
    monkeypatch.setattr(bot_reader,'read_json',failed)
    monkeypatch.setattr(sys,'argv',['grok_query.py','refresh_and_analyze'])
    with pytest.raises(SystemExit):bot_reader.main()
    body=json.loads(capsys.readouterr().out)
    assert body['code']=='missing_target_data'
    assert body['consumer_intent']=='blocked'
