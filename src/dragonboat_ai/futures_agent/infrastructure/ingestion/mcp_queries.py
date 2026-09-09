"""Read-only MCP research queries, separate from futures ingestion/scoring."""
from __future__ import annotations
import json
import math
import re
from .mcp_source import McpFuturesSource, day, fail


class McpMarketQueries:
    def __init__(self, *, transport=None):
        self.source = McpFuturesSource(transport=transport)

    def close(self):
        self.source.close()

    def _query(self, tool, args, provider):
        result = self.source.transport.call_tool(tool, args)
        try:
            if not isinstance(result, dict) or result.get('isError'):
                fail('MCP_TOOL_ERROR')
            texts = [item['text'] for item in result['content'] if item.get('type') == 'text']
            if len(texts) != 1:
                fail('MCP_PROTOCOL_ERROR')
            envelope = json.loads(texts[0])
            if not isinstance(envelope, dict):
                fail('MCP_PROTOCOL_ERROR')
            if envelope.get('ok') is not True:
                code = envelope.get('code')
                fail(code if code in {'NO_ENABLED_PROVIDER','RATE_LIMIT','UNSUPPORTED_ADJUSTMENT','PARAM_VALIDATION_ERROR','CANCELLED','NO_RESULTS'} else 'MCP_TOOL_ERROR')
            data, meta = envelope['data'], envelope['meta']
            if not isinstance(data, dict) or not isinstance(meta, dict):
                fail('MCP_PROTOCOL_ERROR')
            if data.get('source') != provider or not isinstance(meta.get('request_id'), str):
                fail()
            if type(data.get('complete')) is not bool or data.get('completeness') not in {'complete','empty','incomplete'}:
                fail('MCP_INCOMPLETE')
            if data['complete'] and data['completeness'] == 'incomplete':
                fail()
            # Return the entire contract, including provider semantics and gaps.
            return {'ok':True, 'data':data, 'meta':meta, 'scope':'market_data_query'}
        except (KeyError, TypeError, ValueError, AttributeError):
            fail('MCP_PROTOCOL_ERROR')

    @staticmethod
    def _range(start, end):
        if day(start) > day(end) or (day(end)-day(start)).days > 3660:
            fail('PARAM_VALIDATION_ERROR')

    def price_history(self, *, asset_type, code, start, end, adjust='none'):
        self._range(start, end)
        if adjust != 'none':
            fail('UNSUPPORTED_ADJUSTMENT')
        code = code.strip().upper()
        if asset_type == 'hk_stock' and re.fullmatch(r'\d{4,5}\.HK', code):
            symbol = (code[1:] if len(code)==8 and code.startswith('0') else code)
        elif asset_type == 'us_stock' and re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,9}', code):
            symbol = code
        else:
            fail('PARAM_VALIDATION_ERROR')
        result = self._query('price_history', dict(asset_type=asset_type,code=code,start=start,end=end,adjust=adjust), 'yahoo')
        data = result['data']
        if data.get('market') != asset_type or data.get('symbol') != symbol:
            fail()
        expected_tz = 'Asia/Hong_Kong' if asset_type == 'hk_stock' else 'America/New_York'
        if data.get('market_timezone') != expected_tz or data.get('adjustment_method') not in {'none','yahoo_adjclose'}:
            fail()
        if data['complete'] is not True:
            fail('MCP_INCOMPLETE')
        rows = data.get('rows')
        if not isinstance(rows, list):
            fail()
        seen = set()
        for row in rows:
            if not isinstance(row,dict) or row.get('symbol') != symbol:
                fail()
            date = day(row.get('trade_date'))
            if not day(start) <= date <= day(end) or date in seen:
                fail()
            seen.add(date)
            for field in ('open','high','low','close','volume','yahoo_adj_close'):
                value = row.get(field)
                if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
                    fail()
        return result

    def _futures(self, tool, collection, *, product, exchange, start, end, **options):
        self._range(start, end)
        if not re.fullmatch(r'[A-Z]{1,12}', product) or exchange not in {'SHFE','DCE','CZCE','CFFEX','INE','GFEX'}:
            fail('PARAM_VALIDATION_ERROR')
        result = self._query(tool,dict(product=product,exchange=exchange,start=start,end=end,**options),'tushare')
        data=result['data']
        if data.get('product') != product or data.get('exchange') != exchange or not isinstance(data.get(collection),list):
            fail()
        return result

    def main_mapping_history(self, *, product, exchange, start, end, mode='strict'):
        if mode not in {'strict','last_known'}:
            fail('PARAM_VALIDATION_ERROR')
        return self._futures('futures_main_mapping_history','records',product=product,exchange=exchange,start=start,end=end,mode=mode)

    def roll_events(self, *, product, exchange, start, end, price_field='settle'):
        if price_field not in {'settle','close'}:
            fail('PARAM_VALIDATION_ERROR')
        return self._futures('futures_roll_events','events',product=product,exchange=exchange,start=start,end=end,price_field=price_field)
