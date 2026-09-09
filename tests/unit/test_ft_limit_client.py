from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareFuturesClient

def test_limit_fetch_splits_long_windows(monkeypatch):
    client=TushareFuturesClient(token='test')
    calls=[]
    def call(api,params,fields=None):
        calls.append((api,params,fields))
        return []
    monkeypatch.setattr(client,'call',call)
    assert client.fetch_price_limits(ts_code='M2701.DCE',start='20250101',end='20260904')==[]
    assert len(calls)>1
    assert all(api=='ft_limit' and params['ts_code']=='M2701.DCE' for api,params,fields in calls)
    assert calls[0][1]['start_date']=='20250101'
    assert calls[-1][1]['end_date']=='20260904'
