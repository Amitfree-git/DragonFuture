import json
import pytest
from tests.integration.test_refresh_service import CalendarSource, service, NOW
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_source import McpFuturesSource
from dragonboat_ai.futures_agent.application.refresh import RefreshError

def supplier_source():
    source = CalendarSource()
    # Match the actual Tushare numeric schema, including float-valued volume.
    for rows in source.bars.values():
        for row in rows:
            for key, value in list(row.items()):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    row[key] = float(value)
    return source

class Gateway:
    def __init__(self):self.source=supplier_source();self.closed=False;self.calls=0;self.broken=False
    def close(self):self.closed=True
    def call_tool(self,name,args):
        self.calls+=1
        if self.broken and name=='tushare_call' and args['api_name']=='fut_daily':
            return {'isError':True,'content':[]}
        if name=='trading_calendar':rows=self.source.fetch_trade_cal(exchange=args['exchange'],start=args['start'],end=args['end'])
        elif name=='futures_price_limits':rows=[]
        elif args['api_name']=='fut_basic':rows=self.source.contracts
        else:rows=self.source.bars[args['params']['ts_code']]
        data={'source':'tushare','rows':rows,'complete':True,'completeness':'complete' if rows else 'empty'}
        if name=='futures_price_limits':data.update(collection_completeness='empty',band_completeness='complete')
        return {'content':[{'type':'text','text':json.dumps({'ok':True,'data':data,'meta':{'request_id':f'req-{self.calls}','schema_version':'1.1.0'}})}]}

def test_mcp_refresh_matches_direct_and_closes_session(database):
    first=service(database,supplier_source()).run(symbol='RB',exchange='SHFE')
    gateway=Gateway();source=McpFuturesSource(transport=gateway)
    second=service(database,source).run(symbol='RB',exchange='SHFE')
    assert second['refresh']['source']=='wind_tushare_mcp'
    assert second['refresh']['mcp_request_count']>0
    assert second['analysis']['input_data_hash']==first['analysis']['input_data_hash']
    assert second['analysis']['risk']==first['analysis']['risk']
    assert gateway.closed


def test_mcp_failure_does_not_publish_data_and_closes_session(database):
    gateway=Gateway();gateway.broken=True
    with pytest.raises(RefreshError):service(database,McpFuturesSource(transport=gateway)).run(symbol='RB',exchange='SHFE')
    assert gateway.closed
    repo=database['market_repository'];ref=repo.resolve_instrument(symbol='RB',exchange='SHFE')
    assert repo.load_curve_snapshots(instrument_id=ref.instrument_id,as_of=NOW,limit=20)==()
