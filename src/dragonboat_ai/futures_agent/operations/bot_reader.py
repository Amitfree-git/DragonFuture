"""Bounded local research HTTP client for Grok Bot's native Mac Shell."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlencode, quote, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


def summarize(payload: dict) -> dict:
    required = ('analysis_id','request','risk','opportunity','data_mode','versions')
    if any(key not in payload for key in required):
        raise ValueError('unversioned or incomplete analysis; refresh the corrected service')
    action=payload['opportunity'].get('action')
    blocked=payload['risk'].get('hard_gate_triggered') is not False or action in {'no_trade','insufficient_data'}
    keys=('analysis_id','core_result_hash','request','selected_contract','data_mode','production_ready','data_quality','regime','direction','confidence','risk','opportunity','invalidation_conditions','versions')
    result={key:payload.get(key) for key in keys}
    result['production_ready']=False
    result['consumer_intent']='blocked' if blocked else 'research_only'
    result['usage']='Experimental market research; preserve action and risk gates. No order execution.'
    as_of=datetime.fromisoformat(payload['request']['as_of'].replace('Z','+00:00'))
    if as_of.tzinfo is None:
        raise ValueError('analysis as_of must be timezone aware')
    result['age_hours']=round((datetime.now(timezone.utc)-as_of).total_seconds()/3600,2)
    result['stale']=result['age_hours'] > 7*24
    if result['stale']:
        result['consumer_intent']='blocked_stale'
    return result


def read_json(base: str, path: str, *, payload: dict | None = None) -> dict:
    parsed=urlparse(base)
    if parsed.scheme!='http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username or parsed.password:
        raise ValueError('only local loopback HTTP is supported')
    if payload is not None and path != '/refresh_and_analyze':
        raise ValueError('POST is restricted to refresh_and_analyze')
    headers={'Accept':'application/json'}
    if payload is not None:
        headers['Content-Type']='application/json'
    token=os.getenv('DRAGONBOAT_FUTURES_API_TOKEN')
    if token:
        headers['Authorization']='Bearer '+token
    request=Request(base.rstrip('/')+'/api/v1/futures'+path,headers=headers,
                    data=json.dumps(payload).encode('utf-8') if payload is not None else None,
                    method='POST' if payload is not None else 'GET')
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError('redirects are not supported')
    with build_opener(NoRedirect).open(request,timeout=180 if payload is not None else 10) as response:
        if urlparse(response.url).hostname != parsed.hostname:
            raise ValueError('unexpected redirect')
        raw=response.read(2_000_001)
        if len(raw)>2_000_000:
            raise ValueError('response exceeds reader limit')
        return json.loads(raw)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status','latest','invalidation','refresh_and_analyze'])
    parser.add_argument('--symbol',default='RB')
    parser.add_argument('--exchange',default='SHFE')
    parser.add_argument('--horizon',choices=['swing','position'],default='swing')
    parser.add_argument('--as-of')
    parser.add_argument('--analysis-id')
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    try:
        if args.command=='status':
            result=read_json(args.base_url,'/catalog')
        elif args.command=='refresh_and_analyze':
            if args.as_of or args.analysis_id:
                raise ValueError('refresh uses the current clock; --as-of/--analysis-id are not supported')
            body=read_json(args.base_url,'/refresh_and_analyze',payload={
                'symbol':args.symbol.strip().upper(),'exchange':args.exchange.strip().upper(),'horizon':args.horizon})
            analysis=summarize(body['analysis'])
            catalog=read_json(args.base_url,'/catalog')
            if analysis['versions'].get('code_commit')!=catalog['code_artifact']:
                raise ValueError('analysis code artifact mismatch')
            result={'refresh':body['refresh'],'analysis':analysis}
        elif args.command=='latest':
            query={'exchange':args.exchange,'horizon':args.horizon,'as_of':args.as_of or datetime.now(timezone.utc).isoformat()}
            body=read_json(args.base_url,f'/symbols/{quote(args.symbol.upper(),safe="")}/latest?'+urlencode(query))
            result=summarize(body)
            catalog=read_json(args.base_url,'/catalog')
            if result['versions'].get('code_commit')!=catalog['code_artifact']:
                raise ValueError('analysis was generated by a different code artifact; regenerate before use')
        else:
            if not args.analysis_id:
                raise ValueError('--analysis-id is required')
            result=read_json(args.base_url,f'/analyses/{quote(args.analysis_id,safe="")}/invalidation')
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    except HTTPError as exc:
        code='http_error'
        try:
            raw=exc.read(4097)
            detail=json.loads(raw)['detail'] if len(raw)<=4096 else {}
            candidate=detail.get('code') if isinstance(detail,dict) else None
            if isinstance(candidate,str) and len(candidate)<=80 and all(c.isalnum() or c=='_' for c in candidate):
                code=candidate
        except (ValueError,KeyError,TypeError):
            pass
        print(json.dumps({'status':'unavailable','consumer_intent':'blocked','http_status':exc.code,'code':code}))
        sys.exit(1)
    except (URLError,ValueError,KeyError,TimeoutError) as exc:
        print(json.dumps({'status':'unavailable','consumer_intent':'blocked','error':str(exc)},ensure_ascii=False))
        sys.exit(1)


if __name__=='__main__':
    main()
