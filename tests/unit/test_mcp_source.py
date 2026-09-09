import json
import pytest
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_source import McpFuturesSource, configured_source
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError

class Transport:
    def __init__(self, rows=None, **data):
        self.calls=[]; self.closed=False
        self.result={'ok':True,'meta':{'request_id':'test-request','schema_version':'1.1.0'},
                     'data':{'source':'tushare','complete':True,'completeness':'complete','rows':rows or [], **data}}
    def call_tool(self,name,args):
        self.calls.append((name,args));return {'content':[{'type':'text','text':json.dumps(self.result)}]}
    def close(self):self.closed=True

def test_explicit_daily_preserves_null_and_uses_generic_raw_api():
    row={'ts_code':'M2701.DCE','trade_date':'20260904','settle':3200,'open':None}
    t=Transport([row]);s=McpFuturesSource(transport=t)
    assert s.fetch_daily_bars(ts_code='M2701.DCE',start='20260904',end='20260904')==[row]
    assert t.calls[0][1]['api_name']=='fut_daily'
    assert s.provenance[0]['request_id']=='test-request'
    s.close();assert t.closed

@pytest.mark.parametrize('row',[
 {'ts_code':'RB2701.SHF','trade_date':'20260904'},
 {'ts_code':'M2701.DCE','trade_date':'20260230'},
 {'ts_code':'M2701.DCE','trade_date':'20260905'},
])
def test_daily_identity_and_range_rejected(row):
    with pytest.raises(TushareRequestError):McpFuturesSource(transport=Transport([row])).fetch_daily_bars(ts_code='M2701.DCE',start='20260904',end='20260904')

@pytest.mark.parametrize('mode',['business','protocol','truncated','missing_rows'])
def test_fail_closed(mode):
    t=Transport()
    if mode=='business':t.result={'ok':False,'code':'AUTH_ERROR','message':'SECRET'}
    elif mode=='protocol':t.call_tool=lambda *a:{'isError':True,'content':[]}
    elif mode=='truncated':t.result['data'].update(complete=False,completeness='truncated')
    else:t.result['data'].pop('rows')
    with pytest.raises(TushareRequestError) as e:McpFuturesSource(transport=t).fetch_daily_bars(ts_code='M2701.DCE',start='20260904',end='20260904')
    assert 'SECRET' not in str(e.value)

def test_missing_limit_is_preserved_and_canonical_fields_match_direct():
    row={'ts_code':'M2701.DCE','trade_date':'20260904','up_limit':None,'down_limit':None,'pre_close':None,'band_status':'missing'}
    t=Transport([row],complete=False,collection_completeness='complete',band_completeness='partial')
    assert McpFuturesSource(transport=t).fetch_price_limits(ts_code='M2701.DCE',start='20260904',end='20260904')==[{k:row[k] for k in ('ts_code','trade_date','up_limit','down_limit')}]

def test_calendar_incomplete_rejected():
    with pytest.raises(TushareRequestError):McpFuturesSource(transport=Transport([],calendar_complete=False,complete=False)).fetch_trade_cal(exchange='DCE',start='20260904',end='20260904')

def test_source_choice_explicit(monkeypatch):
    monkeypatch.setenv('DRAGONBOAT_FUTURES_SOURCE','unknown')
    with pytest.raises(TushareRequestError):configured_source()

@pytest.mark.parametrize('method,numeric',[('fetch_daily_bars',{'settle':3402,'vol':1781974}),('fetch_price_limits',{'up_limit':3589,'down_limit':3183})])
def test_mcp_integer_serialization_does_not_create_false_revisions(method,numeric):
    from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash
    row={'ts_code':'M2701.DCE','trade_date':'20260904',**numeric}
    extra={'collection_completeness':'complete','band_completeness':'complete'} if method=='fetch_price_limits' else {}
    source=McpFuturesSource(transport=Transport([row],**extra))
    result=getattr(source,method)(ts_code='M2701.DCE',start='20260904',end='20260904')[0]
    direct={**row,**{k:float(v) for k,v in numeric.items()}}
    assert stable_payload_hash(result)==stable_payload_hash(direct)
