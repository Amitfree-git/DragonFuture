"""Fail-closed, serialized refresh followed by deterministic current analysis."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import fcntl
from pathlib import Path
import threading
from contextlib import suppress

from dragonboat_ai.futures_agent.contracts.mapping_pipeline import build_mapping_and_continuous, calendar_from_trade_cal, ingest_trade_calendar
from dragonboat_ai.futures_agent.domain.exceptions import DataNotFoundError
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.infrastructure.database.calendar_store import SqlAlchemyCalendarStore
from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareRequestError
from dragonboat_ai.futures_agent.infrastructure.ingestion.mcp_source import configured_source
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import SHANGHAI, map_contract_basic, parse_trade_date, settlement_available_at


class RefreshError(RuntimeError):
    def __init__(self, code: str, status_code: int = 503):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class RefreshAndAnalyzeService:
    _memory_lock = threading.Lock()

    def __init__(self, repository, analyst, *, source_factory=None, clock=None):
        self.repository = repository
        self.analyst = analyst
        self.source_factory = source_factory or configured_source
        self.clock = clock or (lambda: datetime.now(SHANGHAI))

    @contextmanager
    def _locked(self):
        bind = self.repository.session_factory.kw.get('bind')
        database = bind.url.database if bind is not None else None
        if not database or database == ':memory:':
            if not self._memory_lock.acquire(blocking=False):
                raise RefreshError('REFRESH_IN_PROGRESS', 409)
            try:
                yield
            finally:
                self._memory_lock.release()
            return
        path = Path(database).resolve()
        with path.with_name(path.name + '.refresh.lock').open('a') as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RefreshError('REFRESH_IN_PROGRESS', 409) from None
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def run(self, *, symbol: str, exchange: str, horizon: str = 'swing') -> dict:
        source = None
        try:
            with self._locked():
                source = self.source_factory()
                return self._run(symbol=symbol, exchange=exchange, horizon=horizon, source=source)
        except RefreshError:
            raise
        except TushareRequestError as exc:
            raise RefreshError('SOURCE_AUTH_ERROR' if exc.code == 'AUTH_ERROR' else 'SOURCE_UNAVAILABLE') from None
        except Exception:
            # Provider errors may contain request bodies or credentials.
            raise RefreshError('REFRESH_FAILED') from None
        finally:
            close = getattr(source, 'close', None)
            if callable(close):
                with suppress(Exception):
                    close()

    def _run(self, *, symbol, exchange, horizon, source):
        now = self.clock().astimezone(SHANGHAI)
        request = AnalysisRequest(symbol=symbol, exchange=exchange, horizon=horizon, as_of=now,
                                  include_narrative=False, force_refresh=False)
        symbol, exchange = request.symbol, request.exchange
        repo = self.repository
        try:
            instrument = repo.resolve_instrument(symbol=symbol, exchange=exchange)
            curves = repo.load_curve_snapshots(instrument_id=instrument.instrument_id, as_of=now, limit=100000)
        except DataNotFoundError:
            curves = ()
        bootstrap = now.date() - timedelta(days=365)
        start = curves[-1].trading_date - timedelta(days=10) if curves else bootstrap
        calendar_start = min(start, curves[0].trading_date) if curves else start
        calendar_end = now.date() + timedelta(days=14)
        rows = source.fetch_trade_cal(exchange=exchange, start=calendar_start.strftime('%Y%m%d'), end=calendar_end.strftime('%Y%m%d'))
        days = {}
        for row in rows:
            try:
                day = parse_trade_date(str(row['cal_date']))
                flag = str(row['is_open'])
            except (KeyError, ValueError, TypeError):
                raise RefreshError('INVALID_CALENDAR') from None
            if row.get('exchange') != exchange or flag not in {'0', '1', '0.0', '1.0'} or day in days:
                raise RefreshError('INVALID_CALENDAR')
            days[day] = flag in {'1', '1.0'}
        required = {calendar_start + timedelta(days=i) for i in range((calendar_end-calendar_start).days+1)}
        if set(days) != required:
            raise RefreshError('INCOMPLETE_CALENDAR')
        published = [day for day, opened in days.items() if opened and settlement_available_at(day) <= now]
        if not published:
            raise RefreshError('NO_PUBLISHED_SESSION')
        target = max(published)
        if not any(opened and day > target for day, opened in days.items()):
            raise RefreshError('INCOMPLETE_CALENDAR')
        captured = _CapturedSource(source)
        ingestor = TushareMarketIngestor(repo, captured, clock=self.clock)
        report = ingestor.ingest(product=symbol, exchange=exchange, start=start.strftime('%Y%m%d'),
                                 end=target.strftime('%Y%m%d'), commit=False)
        expected = {day for day, opened in days.items() if opened and start <= day <= target}
        observed = set(report.coverage.observed_trading_dates) if report.coverage else set()
        if observed != expected or target not in observed or report.bars_dropped_missing:
            raise RefreshError('INCOMPLETE_MARKET_DATA')
        prior_points = {point.contract: point for curve in curves[-1:] for point in curve.points}
        for row in captured.contracts:
            # fut_basic also includes product continuous/index aliases (RB/RBL).
            # Only these exact undated aliases are exempt; malformed delivery
            # contracts must still fail the completeness check below.
            code = str(row.get('ts_code') or '').split('.')[0].upper()
            if (code in {symbol, symbol + 'L'}
                    and str(row.get('symbol') or code).upper() == code
                    and str(row.get('fut_code') or '').upper() == symbol
                    and not any(row.get(field) for field in ('list_date', 'delist_date', 'd_month'))):
                continue
            meta = map_contract_basic(row)
            if meta is None:
                raise RefreshError('INCOMPLETE_MARKET_DATA')
            prior = prior_points.get(meta.contract_code)
            contract_rows = [item for item in captured.rows if item.get('ts_code') == meta.ts_code]
            if prior is not None and prior.volume == 0 and not any(float(item.get('vol') or 0) > 0 for item in contract_rows):
                continue
            active_dates = {day for day in expected
                            if (meta.listed_date is None or meta.listed_date <= day)
                            and (meta.last_trade_date is None or day <= meta.last_trade_date)}
            contract_dates = {parse_trade_date(str(item['trade_date'])) for item in contract_rows}
            if not active_dates <= contract_dates:
                raise RefreshError('INCOMPLETE_MARKET_DATA')
        # Preserve every previously liquid, still listed contract at the target.
        # Zero-volume dormant contracts are not required merely because they exist.
        required_contracts = {point.contract for curve in curves[-1:] for point in curve.points
                              if point.volume > 0 and point.open_interest > 0 and point.expiry_date >= target}
        target_contracts = {str(row.get('ts_code', '')).split('.')[0].upper()
                            for row in captured.rows if str(row.get('trade_date')) == target.strftime('%Y%m%d')}
        if not required_contracts <= target_contracts:
            raise RefreshError('INCOMPLETE_MARKET_DATA')
        provenance = getattr(source, 'provenance', [])
        if provenance:
            from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash
            ingestor.manifests.archive_raw(
                provider='wind_tushare_mcp',
                request_digest=stable_payload_hash({'manifest_id': report.manifest_id}),
                response_hash=stable_payload_hash(provenance), received_at=self.clock(),
                license_id='tushare-env', storage_uri=ingestor._archive_response(provenance),
            )
        ingestor.manifests.commit(report.manifest_id)
        completed = self.clock().astimezone(SHANGHAI)
        visible = repo.load_curve_snapshots(instrument_id=report.instrument_id, as_of=completed, limit=100000)
        if not visible or visible[-1].trading_date != target:
            raise RefreshError('TARGET_SESSION_UNAVAILABLE')
        mapping_end = min(day for day, opened in days.items() if opened and day > target)
        mapping_rows = [row for row in rows if visible[0].trading_date <= parse_trade_date(str(row['cal_date'])) <= mapping_end]
        calendar = calendar_from_trade_cal(mapping_rows, exchange=exchange)
        # Every date is explicit, including any exceptional weekend session.
        calendar.weekend_as_holiday = False
        ingest_trade_calendar(SqlAlchemyCalendarStore(repo.session_factory), rows)
        build_mapping_and_continuous(repo, symbol=symbol, exchange=exchange, as_of=completed, calendar=calendar, config=getattr(self.analyst, 'config', None))
        visible = repo.load_curve_snapshots(instrument_id=report.instrument_id, as_of=completed, limit=100000)
        if not visible or visible[-1].trading_date != target:
            raise RefreshError('TARGET_SESSION_UNAVAILABLE')
        result = self.analyst.analyze(request.model_copy(update={'as_of': self.clock().astimezone(SHANGHAI)}))
        return {'refresh': {
            'status': 'updated' if report.bars_inserted or report.bars_revised or report.curves else 'up_to_date',
            'source': getattr(source, 'source_name', 'tushare_http'), 'data_mode': 'final_only',
            'mcp_request_count': len(provenance),
            'mcp_request_ids': [p['request_id'] for p in provenance],
            'target_session': target.isoformat(), 'latest_session': visible[-1].trading_date.isoformat(),
            'started_at': now.isoformat(), 'completed_at': completed.isoformat(),
            'refresh_start': start.isoformat(), 'bars_inserted': report.bars_inserted,
            'bars_revised': report.bars_revised, 'bars_skipped': report.bars_skipped,
            'bars_partial_ohlc': report.bars_partial_ohlc,
            'bars_with_price_limits': report.bars_with_price_limits,
            'bars_missing_price_limits': report.bars_missing_price_limits,
            'price_limits_source': 'tushare.ft_limit',
            'manifest_id': report.manifest_id,
        }, 'analysis': result.model_dump(mode='json')}


class _CapturedSource:
    def __init__(self, source):
        self.source = source
        self.rows = []
        self.contracts = []

    def __getattr__(self, name):
        return getattr(self.source, name)

    def list_contracts(self, **kwargs):
        self.contracts = self.source.list_contracts(**kwargs)
        return self.contracts

    def fetch_daily_bars(self, **kwargs):
        rows = self.source.fetch_daily_bars(**kwargs)
        self.rows.extend(rows)
        return rows
