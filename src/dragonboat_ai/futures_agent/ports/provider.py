from __future__ import annotations

from dataclasses import dataclass

from dragonboat_ai.futures_agent.domain.exceptions import FuturesAgentError


class CapabilityError(FuturesAgentError):
    """Raised when a provider is asked for an ability it does not have."""


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    daily_bars: bool = False
    contracts: bool = False
    specs: bool = False
    calendar: bool = False
    historical_vintage: bool = False

    def require(self, **needed: bool) -> None:
        missing = [name for name, required in needed.items() if required and not getattr(self, name)]
        if missing:
            raise CapabilityError(
                "provider is missing required capabilities: " + ", ".join(sorted(missing))
            )


TUSHARE_CAPABILITIES = ProviderCapabilities(
    daily_bars=True,
    contracts=True,
    specs=False,
    calendar=False,
    historical_vintage=False,
)
