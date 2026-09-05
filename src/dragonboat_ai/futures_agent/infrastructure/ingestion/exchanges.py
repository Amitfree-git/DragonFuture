from __future__ import annotations

from dataclasses import dataclass


EXCHANGE_TO_TUSHARE_SUFFIX = {
    "SHFE": "SHF",
    "CZCE": "ZCE",
    "CFFEX": "CFX",
    "DCE": "DCE",
    "INE": "INE",
    "GFEX": "GFE",
}

TUSHARE_SUFFIX_TO_EXCHANGE = {
    suffix: exchange for exchange, suffix in EXCHANGE_TO_TUSHARE_SUFFIX.items()
}


@dataclass(frozen=True, slots=True)
class ParsedTsCode:
    ts_code: str
    contract_code: str
    suffix: str
    exchange: str


def tushare_suffix(exchange: str) -> str:
    key = exchange.strip().upper()
    try:
        return EXCHANGE_TO_TUSHARE_SUFFIX[key]
    except KeyError as exc:
        raise ValueError(f"Unknown exchange: {exchange}") from exc


def exchange_from_tushare_suffix(suffix: str) -> str:
    key = suffix.strip().upper()
    try:
        return TUSHARE_SUFFIX_TO_EXCHANGE[key]
    except KeyError as exc:
        raise ValueError(f"Unknown Tushare exchange suffix: {suffix}") from exc


def parse_ts_code(ts_code: str) -> ParsedTsCode:
    normalized = ts_code.strip().upper()
    if "." not in normalized:
        raise ValueError(f"Tushare ts_code must include an exchange suffix: {ts_code}")
    contract_code, suffix = normalized.rsplit(".", 1)
    if not contract_code or not suffix:
        raise ValueError(f"Invalid Tushare ts_code: {ts_code}")
    return ParsedTsCode(
        ts_code=normalized,
        contract_code=contract_code,
        suffix=suffix,
        exchange=exchange_from_tushare_suffix(suffix),
    )
