from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from dragonboat_ai.futures_agent.domain.market_data import DailyBar
from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
from dragonboat_ai.futures_agent.ports.provider import CapabilityError, ProviderCapabilities, TUSHARE_CAPABILITIES

SHANGHAI = ZoneInfo("Asia/Shanghai")

RB2610_BASIC = {
    "ts_code": "RB2610.SHF",
    "symbol": "RB2610",
    "exchange": "SHFE",
    "name": "螺纹钢2610",
    "fut_code": "RB",
    "list_date": "20251016",
    "delist_date": "20261015",
    "d_month": "202610",
}
RB2701_BASIC = {
    "ts_code": "RB2701.SHF",
    "symbol": "RB2701",
    "exchange": "SHFE",
    "name": "螺纹钢2701",
    "fut_code": "RB",
    "list_date": "20260116",
    "delist_date": "20270115",
    "d_month": "202701",
}
RB2705_BASIC = {
    "ts_code": "RB2705.SHF",
    "symbol": "RB2705",
    "exchange": "SHFE",
    "name": "螺纹钢2705",
    "fut_code": "RB",
    "list_date": "20260516",
    "delist_date": "20270515",
    "d_month": "202705",
}


def _bar(ts_code: str, trade_date: str, settle: float, close: float, vol: int, oi: int, amount: float) -> dict:
    return {
        "ts_code": ts_code,
        "trade_date": trade_date,
        "pre_settle": settle,
        "open": settle,
        "high": settle + 10,
        "low": settle - 10,
        "close": close,
        "settle": settle,
        "vol": vol,
        "amount": amount,
        "oi": oi,
    }


class FakeFuturesSource:
    def __init__(
        self,
        contracts: list[dict],
        bars: dict[str, list[dict]],
        *,
        capabilities: ProviderCapabilities | None = None,
    ) -> None:
        self.contracts = contracts
        self.bars = bars
        self._capabilities = capabilities or TUSHARE_CAPABILITIES
        self.bar_requests: list[tuple[str, str, str]] = []

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    def list_contracts(self, *, product: str, exchange: str) -> list[dict]:
        return [
            row
            for row in self.contracts
            if row["fut_code"] == product and row["exchange"] == exchange
        ]

    def fetch_daily_bars(self, *, ts_code: str, start: str, end: str) -> list[dict]:
        self.bar_requests.append((ts_code, start, end))
        return [
            row
            for row in self.bars.get(ts_code, [])
            if start <= row["trade_date"] <= end
        ]


def _source() -> FakeFuturesSource:
    return FakeFuturesSource(
        contracts=[RB2610_BASIC, RB2701_BASIC, RB2705_BASIC],
        bars={
            "RB2610.SHF": [
                _bar("RB2610.SHF", "20260901", 3122, 3123, 616523, 814291, 1925241.738),
                _bar("RB2610.SHF", "20260902", 3110, 3091, 380522, 693217, 1183674.63),
            ],
            "RB2701.SHF": [
                _bar("RB2701.SHF", "20260901", 3175, 3174, 710896, 1290303, 2257570.226),
                _bar("RB2701.SHF", "20260902", 3158, 3142, 908468, 1402797, 2869314.246),
            ],
            "RB2705.SHF": [
                _bar("RB2705.SHF", "20260901", 3200, 3201, 10000, 20000, 10.0),
                _bar("RB2705.SHF", "20260902", 3210, 3211, 11000, 21000, 11.0),
            ],
        },
    )


def test_missing_capability_is_explicit(database) -> None:
    source = FakeFuturesSource([], {}, capabilities=ProviderCapabilities())
    with pytest.raises(CapabilityError, match="daily_bars"):
        TushareMarketIngestor(database["market_repository"], source).ingest(
            product="RB",
            exchange="SHFE",
            start="20260901",
            end="20260902",
        )


def test_ingest_skips_out_of_window_and_keeps_full_curve(database) -> None:
    source = _source()
    report = TushareMarketIngestor(database["market_repository"], source).ingest(
        product="RB",
        exchange="SHFE",
        start="20260901",
        end="20260902",
    )
    assert report.contracts == 3
    instrument = database["market_repository"].resolve_instrument(symbol="RB", exchange="SHFE")
    curves = database["market_repository"].load_curve_snapshots(
        instrument_id=instrument.instrument_id,
        as_of=datetime(2026, 9, 2, 16, 30, tzinfo=SHANGHAI),
        limit=10,
    )
    assert [curve.trading_date for curve in curves] == [date(2026, 9, 1), date(2026, 9, 2)]
    for curve in curves:
        assert {point.contract for point in curve.points} == {"RB2610", "RB2701", "RB2705"}
        assert len(curve.points) == 3


def test_manifest_read_is_atomic(database) -> None:
    source = _source()
    repo = database["market_repository"]
    ingestor = TushareMarketIngestor(repo, source)
    report = ingestor.ingest(
        product="RB",
        exchange="SHFE",
        start="20260901",
        end="20260902",
        commit=False,
    )
    contract = repo.resolve_contract(symbol="RB", contract_code="RB2701", exchange="SHFE")
    as_of = datetime(2026, 9, 2, 16, 30, tzinfo=SHANGHAI)
    assert repo.load_contract_bars(contract_id=contract.contract_id, as_of=as_of, limit=10) == ()
    from dragonboat_ai.futures_agent.infrastructure.database.manifest import SqlAlchemyManifestStore

    SqlAlchemyManifestStore(database["session_factory"]).commit(report.manifest_id)
    bars = repo.load_contract_bars(contract_id=contract.contract_id, as_of=as_of, limit=10)
    assert len(bars) == 2


def test_identical_ingest_is_idempotent(database) -> None:
    source = _source()
    repo = database["market_repository"]
    ingestor = TushareMarketIngestor(repo, source)
    first = ingestor.ingest(product="RB", exchange="SHFE", start="20260901", end="20260902")
    second = ingestor.ingest(product="RB", exchange="SHFE", start="20260901", end="20260902")
    assert first.bars_inserted == 6
    assert second.bars_inserted == 0
    assert second.bars_skipped == 6


def test_changed_payload_appends_revision_instead_of_overwrite(database) -> None:
    source = _source()
    repo = database["market_repository"]
    clock = {"now": datetime(2026, 9, 3, 10, 0, tzinfo=SHANGHAI)}
    ingestor = TushareMarketIngestor(repo, source, clock=lambda: clock["now"])
    ingestor.ingest(product="RB", exchange="SHFE", start="20260901", end="20260901")
    source.bars["RB2701.SHF"][0] = _bar("RB2701.SHF", "20260901", 3200, 3199, 710896, 1290303, 2257570.226)
    clock["now"] = datetime(2026, 9, 5, 9, 0, tzinfo=SHANGHAI)
    report = ingestor.ingest(product="RB", exchange="SHFE", start="20260901", end="20260901")
    assert report.bars_revised == 1
    contract = repo.resolve_contract(symbol="RB", contract_code="RB2701", exchange="SHFE")
    before = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        source="tushare",
        limit=10,
    )
    after = repo.load_contract_bars(
        contract_id=contract.contract_id,
        as_of=datetime(2026, 9, 5, 8, 0, tzinfo=timezone.utc),
        source="tushare",
        limit=10,
    )
    assert before[0].settlement == Decimal("3175")
    assert before[0].revision_no == 1
    assert after[0].settlement == Decimal("3200")
    assert after[0].revision_no == 2


def test_latest_visible_revision_per_source(database) -> None:
    repo = database["market_repository"]
    instrument_id = repo.get_or_create_instrument(exchange="SHFE", symbol="RB")
    contract = repo.get_or_create_contract(
        instrument_id=instrument_id,
        contract_code="RB2701",
        expiry_date=date(2027, 1, 15),
    )
    price = Decimal("3500")

    def bar(source: str, settlement: str, revision: int, day: int) -> DailyBar:
        value = Decimal(settlement)
        return DailyBar(
            contract_id=contract.contract_id,
            contract="RB2701",
            trading_date=date(2026, 1, 2),
            open=value,
            high=value,
            low=value,
            close=value,
            settlement=value,
            previous_settlement=None,
            volume=100,
            turnover=None,
            open_interest=200,
            upper_limit=None,
            lower_limit=None,
            revision_no=revision,
            available_at=datetime(2026, 1, day, 8, 0, tzinfo=timezone.utc),
            source=source,
            payload_hash=f"{source}-{settlement}",
        )

    repo.add_daily_bar(bar("tushare", "3500", 1, 3))
    repo.add_daily_bar(bar("tushare", "3550", 2, 5))
    repo.add_daily_bar(bar("wind", "3600", 1, 4))
    as_of = datetime(2026, 1, 6, 8, 0, tzinfo=timezone.utc)
    tushare = repo.load_contract_bars(contract_id=contract.contract_id, as_of=as_of, source="tushare", limit=10)
    wind = repo.load_contract_bars(contract_id=contract.contract_id, as_of=as_of, source="wind", limit=10)
    assert tushare[0].settlement == Decimal("3550")
    assert wind[0].settlement == Decimal("3600")


def test_coverage_report_lists_weekday_gaps(database) -> None:
    source = FakeFuturesSource(
        contracts=[RB2701_BASIC],
        bars={"RB2701.SHF": [_bar("RB2701.SHF", "20260901", 3175, 3174, 100, 100, 1.0)]},
    )
    report = TushareMarketIngestor(database["market_repository"], source).ingest(
        product="RB",
        exchange="SHFE",
        start="20260901",
        end="20260903",
    )
    assert report.coverage is not None
    assert date(2026, 9, 2) in report.coverage.missing_trading_dates
    assert date(2026, 9, 1) in report.coverage.observed_trading_dates
