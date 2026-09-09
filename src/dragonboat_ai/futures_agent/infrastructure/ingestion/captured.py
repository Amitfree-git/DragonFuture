from __future__ import annotations

import json
from pathlib import Path

from dragonboat_ai.futures_agent.ports.market_source import StaticCapabilitySource


class CapturedFuturesSource(StaticCapabilitySource):
    """Replay a local Tushare/MCP capture. Commercial dumps stay outside git."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        basic_path = self.root / "fut_basic.json"
        daily_path = self.root / "fut_daily.json"
        if not basic_path.exists() or not daily_path.exists():
            raise FileNotFoundError(f"Capture at {self.root} must include fut_basic.json and fut_daily.json")
        self._contracts = json.loads(basic_path.read_text(encoding="utf-8"))
        daily = json.loads(daily_path.read_text(encoding="utf-8"))
        if isinstance(daily, list):
            grouped: dict[str, list[dict]] = {}
            for row in daily:
                grouped.setdefault(str(row["ts_code"]).upper(), []).append(row)
            self._bars = grouped
        else:
            self._bars = {str(key).upper(): list(value) for key, value in daily.items()}

    def list_contracts(self, *, product: str, exchange: str) -> list[dict]:
        product = product.strip().upper()
        exchange = exchange.strip().upper()
        return [
            row
            for row in self._contracts
            if str(row.get("fut_code") or "").upper() == product
            and str(row.get("exchange") or "").upper() == exchange
        ]

    def fetch_daily_bars(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        rows = self._bars.get(ts_code.strip().upper(), [])
        return [row for row in rows if start <= str(row["trade_date"]) <= end]

    def fetch_price_limits(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        path = self.root / "ft_limit.json"
        if not path.exists():
            return []
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [row for row in rows if str(row.get("ts_code", "")).upper() == ts_code.upper()
                and start <= str(row.get("trade_date", "")) <= end]
