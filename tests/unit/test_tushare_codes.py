import pytest

from dragonboat_ai.futures_agent.infrastructure.ingestion.exchanges import (
    exchange_from_tushare_suffix,
    parse_ts_code,
    tushare_suffix,
)


@pytest.mark.parametrize(
    ("exchange", "suffix"),
    [
        ("SHFE", "SHF"),
        ("CZCE", "ZCE"),
        ("CFFEX", "CFX"),
        ("DCE", "DCE"),
        ("INE", "INE"),
        ("GFEX", "GFE"),
    ],
)
def test_exchange_suffix_round_trip(exchange: str, suffix: str) -> None:
    assert tushare_suffix(exchange) == suffix
    assert exchange_from_tushare_suffix(suffix) == exchange


def test_parse_ts_code_splits_contract_and_exchange() -> None:
    parsed = parse_ts_code("RB2701.SHF")
    assert parsed.ts_code == "RB2701.SHF"
    assert parsed.contract_code == "RB2701"
    assert parsed.suffix == "SHF"
    assert parsed.exchange == "SHFE"


def test_parse_czce_short_year_code() -> None:
    parsed = parse_ts_code("TA601.ZCE")
    assert parsed.contract_code == "TA601"
    assert parsed.exchange == "CZCE"


def test_parse_ts_code_rejects_unknown_suffix() -> None:
    with pytest.raises(ValueError, match="Unknown Tushare exchange suffix"):
        parse_ts_code("RB2701.SHFE")
