"""Validate exact contract/date joins; never infer exchange price bands."""
from decimal import Decimal, InvalidOperation
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import parse_trade_date
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError


def index_price_limits(rows, *, ts_code, start, end):
    indexed = {}
    for row in rows:
        try:
            day = parse_trade_date(str(row["trade_date"]))
            if str(row["ts_code"]).upper() != ts_code.upper() or not start <= day <= end or day in indexed:
                raise ValueError("invalid identity/date")
            values = tuple(Decimal(str(row[name])) if row.get(name) is not None else None
                           for name in ("up_limit", "down_limit"))
            if any(v is not None and (not v.is_finite() or v <= 0) for v in values):
                raise ValueError("invalid price")
            upper, lower = values
            if upper is not None and lower is not None and upper <= lower:
                raise ValueError("inverted or zero price band")
            indexed[day] = (row, upper, lower)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise TushareRequestError("INVALID_LIMIT_DATA", "invalid contract/date limit response") from None
    return indexed
