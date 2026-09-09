from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class TushareRequestError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"Tushare {code}: {message}")
        self.code = str(code)
        self.message = message


class TushareFuturesClient:
    """HTTP client for the Tushare Pro futures interfaces used by ingest."""

    def __init__(
        self,
        token: str | None = None,
        *,
        endpoint: str = "https://api.tushare.pro",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        if not self.token:
            raise TushareRequestError("AUTH_ERROR", "TUSHARE_TOKEN is not configured")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def capabilities(self) -> ProviderCapabilities:
        from dragonboat_ai.futures_agent.ports.provider import TUSHARE_CAPABILITIES

        return TUSHARE_CAPABILITIES

    def list_contracts(self, *, product: str, exchange: str) -> list[dict]:
        return self.call(
            "fut_basic",
            {"exchange": exchange.upper(), "fut_code": product.upper()},
            fields="ts_code,symbol,exchange,name,fut_code,multiplier,list_date,delist_date,d_month,last_ddate",
        )

    def fetch_daily_bars(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        return self.call(
            "fut_daily",
            {"ts_code": ts_code, "start_date": start, "end_date": end},
        )

    def fetch_price_limits(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        # One contract and at most 366 calendar dates per request, below 4000 rows.
        from datetime import datetime, timedelta
        first = datetime.strptime(start, "%Y%m%d").date()
        last = datetime.strptime(end, "%Y%m%d").date()
        rows = []
        while first <= last:
            stop = min(first + timedelta(days=365), last)
            chunk = self.call("ft_limit", {
                "ts_code": ts_code, "start_date": first.strftime("%Y%m%d"),
                "end_date": stop.strftime("%Y%m%d"),
            }, fields="ts_code,trade_date,up_limit,down_limit")
            if len(chunk) >= 4000:
                raise TushareRequestError("LIMIT_RESPONSE_TRUNCATED", "limit response reached provider cap")
            rows.extend(chunk)
            first = stop + timedelta(days=1)
        return rows

    def fetch_trade_cal(self, *, exchange: str, start: str, end: str) -> list[dict]:
        return self.call(
            "trade_cal",
            {"exchange": exchange.upper(), "start_date": start, "end_date": end},
            fields="exchange,cal_date,is_open,pretrade_date",
        )

    def fetch_mapping(self, *, product: str, exchange: str, start: str, end: str) -> list[dict]:
        from dragonboat_ai.futures_agent.infrastructure.ingestion.exchanges import tushare_suffix

        ts_code = f"{product.upper()}.{tushare_suffix(exchange)}"
        return self.call("fut_mapping", {"ts_code": ts_code, "start_date": start, "end_date": end})

    def call(self, api_name: str, params: dict[str, Any], fields: str | None = None) -> list[dict]:
        payload: dict[str, Any] = {
            "api_name": api_name,
            "token": self.token,
            "params": params,
        }
        if fields:
            payload["fields"] = fields
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise TushareRequestError("NETWORK_ERROR", str(exc)) from exc

        code = body.get("code")
        if code not in (0, "0"):
            raise TushareRequestError(
                str(code),
                str(body.get("msg") or body.get("message") or body),
            )

        data = body.get("data") or {}
        if "rows" in data:
            return list(data["rows"])
        fields_list = data.get("fields") or []
        items = data.get("items") or []
        return [dict(zip(fields_list, item, strict=False)) for item in items]
