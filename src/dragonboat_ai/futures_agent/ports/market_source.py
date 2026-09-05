from __future__ import annotations

from typing import Protocol

from dragonboat_ai.futures_agent.ports.provider import ProviderCapabilities, TUSHARE_CAPABILITIES


class FuturesMarketSource(Protocol):
    def capabilities(self) -> ProviderCapabilities:
        ...

    def list_contracts(self, *, product: str, exchange: str) -> list[dict]:
        """Return provider contract master rows for one product."""

    def fetch_daily_bars(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        """Return provider daily bar rows for one contract."""


class StaticCapabilitySource:
    """Mixin-style helper for fakes and the HTTP client."""

    def capabilities(self) -> ProviderCapabilities:
        return TUSHARE_CAPABILITIES
