"""Explicit read-only market queries; not futures analysis requests."""
from contextlib import suppress
from typing import Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_queries import McpMarketQueries
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError
from datetime import datetime
import re

router=APIRouter(prefix='/api/v1/market-data',tags=['market-data'])

class RangeQuery(BaseModel):
    model_config=ConfigDict(extra='forbid')
    start: str
    end: str

    @field_validator('start','end')
    @classmethod
    def date_valid(cls,value):
        if not re.fullmatch(r'(?:[0-9]{8}|[0-9]{4}-[0-9]{2}-[0-9]{2})',value):
            raise ValueError('Use YYYYMMDD or YYYY-MM-DD')
        compact=value.replace('-','')
        if len(compact)!=8 or not compact.isdigit():
            raise ValueError('Use YYYYMMDD or YYYY-MM-DD')
        datetime.strptime(compact,'%Y%m%d')
        return compact

    @model_validator(mode='after')
    def range_valid(self):
        if not 0 <= (datetime.strptime(self.end,'%Y%m%d')-datetime.strptime(self.start,'%Y%m%d')).days <= 3660:
            raise ValueError('Date range must be ordered and at most 3660 days')
        return self

class PriceQuery(RangeQuery):
    asset_type: Literal['hk_stock','us_stock']
    code: str=Field(min_length=1,max_length=16,pattern=r'^[A-Za-z0-9.\-]+$')
    adjust: Literal['none']='none'

class FuturesQuery(RangeQuery):
    product: str=Field(min_length=1,max_length=12,pattern=r'^[A-Z]+$')
    exchange: Literal['SHFE','DCE','CZCE','CFFEX','INE','GFEX']

class MappingQuery(FuturesQuery):
    mode: Literal['strict','last_known']='strict'

class RollQuery(FuturesQuery):
    price_field: Literal['settle','close']='settle'


def execute(request, method, payload):
    source=None
    try:
        factory=getattr(request.app.state,'market_query_factory',McpMarketQueries)
        source=factory()
        return getattr(source,method)(**payload.model_dump())
    except TushareRequestError as exc:
        code=exc.code
        status=429 if code=='RATE_LIMIT' else 422 if code in {'PARAM_VALIDATION_ERROR','UNSUPPORTED_ADJUSTMENT'} else 503
        raise HTTPException(status_code=status,detail={'status':'query_failed','code':code}) from None
    finally:
        if source is not None:
            with suppress(Exception):source.close()

@router.post('/price_history')
def price_history(payload:PriceQuery,request:Request):
    return execute(request,'price_history',payload)

@router.post('/futures_main_mapping_history')
def mapping_history(payload:MappingQuery,request:Request):
    return execute(request,'main_mapping_history',payload)

@router.post('/futures_roll_events')
def roll_events(payload:RollQuery,request:Request):
    return execute(request,'roll_events',payload)
