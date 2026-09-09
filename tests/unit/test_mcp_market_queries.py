import json
import pytest
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_queries import McpMarketQueries
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError

class Transport:
    def __init__(self,data):self.data=data;self.closed=False;self.calls=[]
    def close(self):self.closed=True
    def call_tool(self,name,args):
        self.calls.append((name,args))
        return {'content':[{'type':'text','text':json.dumps({'ok':True,'data':self.data,'meta':{'request_id':'r1'}})}]}

def stock():
    return {'source':'yahoo','market':'hk_stock','symbol':'0700.HK','market_timezone':'Asia/Hong_Kong','currency':'HKD','complete':True,'completeness':'complete','adjustment_method':'yahoo_adjclose','rows':[{'symbol':'0700.HK','trade_date':'20260904','close':500,'yahoo_adj_close':498,'volume':None}]}

def test_hk_normalization_and_adjustment_preserved():
    t=Transport(stock());s=McpMarketQueries(transport=t)
    r=s.price_history(asset_type='hk_stock',code='00700.HK',start='20260901',end='20260904')
    assert r['data']['rows'][0]['yahoo_adj_close']==498
    assert r['data']['rows'][0]['volume'] is None
    assert r['meta']['request_id']=='r1'
    assert t.calls[0][0]=='price_history'

@pytest.mark.parametrize('field,value',[('symbol','AAPL'),('trade_date','20260905')])
def test_wrong_identity_or_range_rejected(field,value):
    d=stock();d['rows'][0][field]=value
    with pytest.raises(TushareRequestError):McpMarketQueries(transport=Transport(d)).price_history(asset_type='hk_stock',code='00700.HK',start='20260901',end='20260904')

def test_truncated_is_not_success():
    d=stock();d.update(complete=False,completeness='truncated')
    with pytest.raises(TushareRequestError):McpMarketQueries(transport=Transport(d)).price_history(asset_type='hk_stock',code='00700.HK',start='20260901',end='20260904')

def test_incomplete_roll_is_returned_as_incomplete_not_discarded():
    d={'source':'tushare','product':'M','exchange':'DCE','complete':False,'completeness':'incomplete','events':[],'boundary_completeness':'incomplete','point_in_time_verified':False}
    s=McpMarketQueries(transport=Transport(d))
    r=s.roll_events(product='M',exchange='DCE',start='20260901',end='20260904')
    assert r['data']['complete'] is False
    assert r['data']['point_in_time_verified'] is False


def test_unsupported_adjustment_rejected_before_network():
    t=Transport(stock())
    with pytest.raises(TushareRequestError):McpMarketQueries(transport=t).price_history(asset_type='hk_stock',code='00700.HK',start='20260901',end='20260904',adjust='qfq')
    assert not t.calls
