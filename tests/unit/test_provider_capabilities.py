import pytest

from dragonboat_ai.futures_agent.ports.provider import CapabilityError, ProviderCapabilities, TUSHARE_CAPABILITIES


def test_tushare_capabilities_refuse_calendar_and_vintage() -> None:
    with pytest.raises(CapabilityError, match="calendar"):
        TUSHARE_CAPABILITIES.require(calendar=True)
    with pytest.raises(CapabilityError, match="historical_vintage"):
        TUSHARE_CAPABILITIES.require(historical_vintage=True)
    TUSHARE_CAPABILITIES.require(daily_bars=True, contracts=True)


def test_empty_provider_refuses_daily_bars() -> None:
    with pytest.raises(CapabilityError, match="daily_bars"):
        ProviderCapabilities().require(daily_bars=True)
