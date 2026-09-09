"""MCP gateway adapter. Supplier remains Tushare; transport is explicit."""
from __future__ import annotations
import hashlib
import json
import os
import math
from datetime import datetime, timedelta
from .mcp_transport import StdioMcpTransport
from .tushare_client import TushareFuturesClient, TushareRequestError
from .exchanges import tushare_suffix
from dragonboat_ai.futures_agent.ports.provider import ProviderCapabilities


def fail(code='MCP_INVALID_DATA'):
    raise TushareRequestError(code, 'MCP market source rejected response')


def day(value):
    if not isinstance(value,str) or len(value)!=8 or not value.isdigit():
        fail()
    try:
        return datetime.strptime(value,'%Y%m%d').date()
    except ValueError:
        fail()


class McpFuturesSource:
    source_name = 'wind_tushare_mcp'
    source_policy = 'tushare_via_mcp'

    def __init__(self, *, transport=None):
        if transport is None:
            try:
                command = json.loads(os.environ['DRAGONBOAT_FUTURES_MCP_COMMAND'])
                timeout = float(os.environ.get('DRAGONBOAT_FUTURES_MCP_TIMEOUT','45'))
                if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command) or not 0 < timeout <= 300:
                    raise ValueError()
            except (KeyError,ValueError,TypeError):
                fail('MCP_CONFIG_ERROR')
            transport = StdioMcpTransport(command, timeout)
        self.transport = transport
        self.provenance = []

    def capabilities(self):
        return ProviderCapabilities(daily_bars=True,contracts=True,calendar=True)

    def close(self):
        self.transport.close()

    def _rows(self, tool, args, *, limits=False):
        result = self.transport.call_tool(tool,args)
        try:
            if result.get('isError'):
                fail('MCP_TOOL_ERROR')
            texts=[c['text'] for c in result['content'] if c.get('type')=='text']
            if len(texts)!=1:
                fail('MCP_PROTOCOL_ERROR')
            envelope=json.loads(texts[0])
            if envelope.get('ok') is not True:
                fail('AUTH_ERROR' if envelope.get('code')=='AUTH_ERROR' else 'MCP_TOOL_ERROR')
            data=envelope['data'];meta=envelope['meta']
            if data.get('source')!='tushare' or not isinstance(meta.get('request_id'),str):
                fail()
            completeness=data.get('collection_completeness') if limits else data.get('completeness')
            if completeness not in {'complete','empty'}:
                fail('MCP_INCOMPLETE')
            if not limits and data.get('complete') is not True:
                fail('MCP_INCOMPLETE')
            if limits and data.get('band_completeness')=='invalid':
                fail()
            rows=data['rows']
            if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):
                fail()
            self.provenance.append({'tool':tool,'arguments':args,'request_id':meta['request_id'],
                'schema_version':meta.get('schema_version'),'server_version':meta.get('server_version'),
                'received_at':meta.get('received_at'),'actual_source':data['source'],
                'raw_response_hash':meta.get('raw_response_hash'),
                'upstream_calls':meta.get('upstream_calls',[]),
                'rows_hash':hashlib.sha256(json.dumps(rows,sort_keys=True,allow_nan=False).encode()).hexdigest()})
            return rows
        except (KeyError,TypeError,ValueError):
            fail('MCP_PROTOCOL_ERROR')

    def list_contracts(self, *, product, exchange):
        fields='ts_code,symbol,exchange,name,fut_code,multiplier,list_date,delist_date,d_month,last_ddate'
        rows=self._rows('tushare_call',{'api_name':'fut_basic','params':{'exchange':exchange,'fut_code':product},'fields':fields})
        seen=set()
        for r in rows:
            if r.get('exchange')!=exchange or r.get('fut_code')!=product or not str(r.get('ts_code','')).endswith('.'+tushare_suffix(exchange)) or r.get('ts_code') in seen:
                fail()
            seen.add(r['ts_code'])
        return rows

    def _contract_rows(self, ts_code, start, end, *, limits=False):
        first,last=day(start),day(end)
        if first>last:
            fail()
        output=[];seen=set()
        while first<=last:
            stop=min(first+timedelta(days=365),last)
            lo,hi=first.strftime('%Y%m%d'),stop.strftime('%Y%m%d')
            if limits:
                rows=self._rows('futures_price_limits',{'ts_code':ts_code,'start':lo,'end':hi},limits=True)
            else:
                rows=self._rows('tushare_call',{'api_name':'fut_daily','params':{'ts_code':ts_code,'start_date':lo,'end_date':hi}})
            for r in rows:
                d=day(r.get('trade_date'))
                if r.get('ts_code')!=ts_code or not first<=d<=stop or d in seen:
                    fail()
                seen.add(d)
                # Strip gateway enrichment so raw hashes match direct ft_limit capture.
                if limits:
                    r={k:r[k] for k in ('ts_code','trade_date','up_limit','down_limit')}
                # Tushare JSON encodes these columns as floating-point values.
                # JavaScript drops .0; restore the supplier schema before hashing
                # to avoid false bar revisions when switching transports.
                numeric_fields = ('up_limit', 'down_limit') if limits else (
                    'pre_close', 'pre_settle', 'open', 'high', 'low', 'close',
                    'settle', 'change1', 'change2', 'vol', 'amount', 'oi', 'oi_chg')
                r = dict(r)
                for key in numeric_fields:
                    value = r.get(key)
                    if value is not None:
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                            fail()
                        r[key] = float(value)
                output.append(r)
            first=stop+timedelta(days=1)
        return sorted(output,key=lambda r:r['trade_date'],reverse=True)

    def fetch_daily_bars(self, *, ts_code, start, end):
        return self._contract_rows(ts_code,start,end)

    def fetch_price_limits(self, *, ts_code, start, end):
        return self._contract_rows(ts_code,start,end,limits=True)

    def fetch_trade_cal(self, *, exchange, start, end):
        first,last=day(start),day(end)
        if first>last:
            fail()
        rows=self._rows('trading_calendar',{'exchange':exchange,'start':start,'end':end})
        seen=set()
        for r in rows:
            d=day(r.get('cal_date'));flag=r.get('is_open')
            if r.get('exchange')!=exchange or isinstance(flag,bool) or flag not in (0,1,'0','1') or d in seen or not first<=d<=last:
                fail()
            seen.add(d)
        if len(seen)!=(last-first).days+1:
            fail('MCP_INCOMPLETE_CALENDAR')
        return rows


def configured_source():
    selected=os.environ.get('DRAGONBOAT_FUTURES_SOURCE','tushare_http')
    if selected=='mcp':
        return McpFuturesSource()
    if selected=='tushare_http':
        return TushareFuturesClient()
    fail('SOURCE_CONFIG_ERROR')
