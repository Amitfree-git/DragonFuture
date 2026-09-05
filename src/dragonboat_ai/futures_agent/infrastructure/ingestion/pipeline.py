from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Callable

from dragonboat_ai.futures_agent.domain.market_data import CurvePoint, CurveSnapshot, DailyBar
from dragonboat_ai.futures_agent.infrastructure.database.manifest import (
    ManifestStatus,
    SqlAlchemyManifestStore,
)
from dragonboat_ai.futures_agent.infrastructure.database.repositories import SqlAlchemyMarketDataRepository
from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import (
    SHANGHAI,
    TUSHARE_SOURCE,
    ContractMeta,
    map_contract_basic,
    map_fut_daily_bar,
    parse_trade_date,
    settlement_available_at,
)
from dragonboat_ai.futures_agent.ports.market_source import FuturesMarketSource


@dataclass(slots=True)
class IngestReport:
    instrument_id: int = 0
    contracts: int = 0
    bars_inserted: int = 0
    bars_skipped: int = 0
    bars_revised: int = 0
    bars_dropped_missing: int = 0
    curves: int = 0
    manifest_id: str | None = None
    coverage: CoverageReport | None = None


@dataclass(frozen=True, slots=True)
class CoverageReport:
    expected_trading_dates: tuple[date, ...]
    observed_trading_dates: tuple[date, ...]
    missing_trading_dates: tuple[date, ...]
    contract_count: int
    notes: tuple[str, ...] = ()


class TushareMarketIngestor:
    def __init__(
        self,
        repository: SqlAlchemyMarketDataRepository,
        source: FuturesMarketSource,
        *,
        manifests: SqlAlchemyManifestStore | None = None,
        clock: Callable[[], datetime] | None = None,
        retries: int = 3,
    ) -> None:
        self.repository = repository
        self.source = source
        self.manifests = manifests or SqlAlchemyManifestStore(repository.session_factory)
        self.clock = clock or (lambda: datetime.now(SHANGHAI))
        self.retries = retries

    def ingest(
        self,
        *,
        product: str,
        exchange: str,
        start: str,
        end: str,
        commit: bool = True,
    ) -> IngestReport:
        self.source.capabilities().require(daily_bars=True, contracts=True)
        product = product.strip().upper()
        exchange = exchange.strip().upper()
        start_date = parse_trade_date(start)
        end_date = parse_trade_date(end)
        report = IngestReport()
        manifest = self.manifests.create(
            manifest_id=f"tushare-{product}-{exchange}-{start}-{end}-{self.clock().strftime('%Y%m%d%H%M%S')}",
            source_policy="tushare_only",
            data_mode="final_only",
            status=ManifestStatus.PENDING,
        )
        report.manifest_id = manifest.manifest_id
        self._ingest_into_batch(
            report=report,
            product=product,
            exchange=exchange,
            start=start,
            end=end,
            start_date=start_date,
            end_date=end_date,
            batch_id=manifest.batch_id,
        )
        if commit:
            self.manifests.commit(manifest.manifest_id)
        return report

    def _ingest_into_batch(
        self,
        *,
        report: IngestReport,
        product: str,
        exchange: str,
        start: str,
        end: str,
        start_date: date,
        end_date: date,
        batch_id: str,
    ) -> None:
        contract_rows = self._retry(lambda: self.source.list_contracts(product=product, exchange=exchange))
        self.manifests.archive_raw(
            provider=TUSHARE_SOURCE,
            request_digest=stable_payload_hash({"api": "fut_basic", "product": product, "exchange": exchange}),
            response_hash=stable_payload_hash(contract_rows),
            received_at=self.clock(),
            license_id="tushare-env",
            storage_uri=f"memory://fut_basic/{product}/{exchange}",
        )
        metas: list[ContractMeta] = []
        for row in contract_rows:
            meta = map_contract_basic(row)
            if meta is None:
                continue
            if _contract_overlaps_window(meta, start_date, end_date):
                metas.append(meta)
        if not metas:
            report.coverage = CoverageReport((), (), (), 0, ("no_contracts_in_window",))
            return

        instrument_id = self.repository.get_or_create_instrument(
            exchange=exchange,
            symbol=product,
            name=metas[0].name,
        )
        report.instrument_id = instrument_id
        report.contracts = len(metas)
        refs = {
            meta.ts_code: self.repository.get_or_create_contract(
                instrument_id=instrument_id,
                contract_code=meta.contract_code,
                expiry_date=meta.expiry_date,
                listed_date=meta.listed_date,
                last_trade_date=meta.last_trade_date,
                delivery_month=meta.delivery_month,
            )
            for meta in metas
        }
        mapped_bars: list[DailyBar] = []
        for meta in metas:
            rows = self._retry(
                lambda ts=meta.ts_code: self.source.fetch_daily_bars(ts_code=ts, start=start, end=end)
            )
            self.manifests.archive_raw(
                provider=TUSHARE_SOURCE,
                request_digest=stable_payload_hash({"api": "fut_daily", "ts_code": meta.ts_code, "start": start, "end": end}),
                response_hash=stable_payload_hash(rows),
                received_at=self.clock(),
                license_id="tushare-env",
                storage_uri=f"memory://fut_daily/{meta.ts_code}/{start}/{end}",
            )
            for row in rows:
                bar = map_fut_daily_bar(row, contract_id=refs[meta.ts_code].contract_id)
                if bar is None:
                    report.bars_dropped_missing += 1
                    continue
                status = self.repository.ingest_daily_bar(
                    bar,
                    data_batch_id=batch_id,
                    correction_available_at=self.clock(),
                )
                if status == "inserted":
                    report.bars_inserted += 1
                elif status == "skipped":
                    report.bars_skipped += 1
                else:
                    report.bars_revised += 1
                mapped_bars.append(bar)

        bars_by_date: dict[date, list[DailyBar]] = defaultdict(list)
        for bar in mapped_bars:
            bars_by_date[bar.trading_date].append(bar)
        refs_by_id = {ref.contract_id: ref for ref in refs.values()}
        for trading_date, bars in sorted(bars_by_date.items()):
            points = tuple(
                CurvePoint(
                    contract_id=bar.contract_id,
                    contract=bar.contract,
                    expiry_date=refs_by_id[bar.contract_id].expiry_date,
                    days_to_expiry=(refs_by_id[bar.contract_id].expiry_date - trading_date).days,
                    settlement=bar.settlement,
                    volume=bar.volume,
                    open_interest=bar.open_interest,
                )
                for bar in bars
            )
            snapshot = CurveSnapshot(
                snapshot_id=f"{product}-{trading_date.isoformat()}-{TUSHARE_SOURCE}",
                instrument_id=instrument_id,
                exchange=exchange,
                symbol=product,
                trading_date=trading_date,
                observed_at=datetime.combine(trading_date, time(15, 0), tzinfo=SHANGHAI),
                available_at=settlement_available_at(trading_date),
                points=points,
                source=TUSHARE_SOURCE,
                input_hash=stable_payload_hash(
                    [
                        {
                            "contract": point.contract,
                            "settlement": str(point.settlement),
                            "volume": point.volume,
                            "open_interest": point.open_interest,
                        }
                        for point in sorted(points, key=lambda item: item.contract)
                    ]
                ),
            )
            if self.repository.ingest_curve_snapshot(
                snapshot,
                data_batch_id=batch_id,
                correction_available_at=self.clock(),
            ) != "skipped":
                report.curves += 1

        expected = _weekdays(start_date, end_date)
        observed = tuple(sorted(bars_by_date))
        report.coverage = CoverageReport(
            expected_trading_dates=expected,
            observed_trading_dates=observed,
            missing_trading_dates=tuple(day for day in expected if day not in bars_by_date),
            contract_count=len(metas),
            notes=("tushare_final_only_no_historical_vintage",),
        )

    def _retry(self, operation: Callable[[], list[dict]]) -> list[dict]:
        last_error: Exception | None = None
        for _ in range(max(self.retries, 1)):
            try:
                return operation()
            except TushareRequestError as exc:
                if exc.code in {"AUTH_ERROR"}:
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error


def _contract_overlaps_window(meta: ContractMeta, start: date, end: date) -> bool:
    listed = meta.listed_date or date.min
    delisted = meta.last_trade_date or date.max
    return listed <= end and delisted >= start


def _weekdays(start: date, end: date) -> tuple[date, ...]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current = current.fromordinal(current.toordinal() + 1)
    return tuple(days)
