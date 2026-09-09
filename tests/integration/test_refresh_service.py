from datetime import date, datetime, timedelta
import pytest
from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from tests.integration.test_tushare_ingest import FakeFuturesSource, SHANGHAI, _source, _bar
NOW = datetime(2026, 9, 3, 10, tzinfo=SHANGHAI)

class CalendarSource(FakeFuturesSource):
    def __init__(self):
        source = _source()
        super().__init__(source.contracts, source.bars)
        self.omit_calendar = False
        self.error = False
    def fetch_trade_cal(self, *, exchange, start, end):
        if self.error:
            raise RuntimeError('secret-provider-token')
        first = datetime.strptime(start, '%Y%m%d').date()
        last = datetime.strptime(end, '%Y%m%d').date()
        return [dict(exchange=exchange, cal_date=day.strftime('%Y%m%d'),
                     is_open=int(day in {date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 7)}))
                for offset in range((last-first).days+1)
                if not self.omit_calendar or offset != 0
                for day in [first+timedelta(days=offset)]]

def service(database, source):
    from dragonboat_ai.futures_agent.application.refresh import RefreshAndAnalyzeService
    repo = database['market_repository']
    analyst = FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(repo), analysis_repository=database['analysis_repository'])
    return RefreshAndAnalyzeService(repo, analyst, source_factory=lambda: source, clock=lambda: NOW)

def test_refresh_uses_calendar_holidays_and_is_idempotent(database):
    runner = service(database, CalendarSource())
    first = runner.run(symbol='RB', exchange='SHFE')
    second = runner.run(symbol='RB', exchange='SHFE')
    assert first['refresh']['status'] == 'updated'
    assert second['refresh']['status'] == 'up_to_date'
    assert first['refresh']['target_session'] == '2026-09-02'
    assert first['analysis']['data_mode'] == 'final_only'
    assert first['analysis']['production_ready'] is False
    assert first['analysis']['request']['include_narrative'] is False
    assert first['analysis']['input_data_hash'] == second['analysis']['input_data_hash']

def test_missing_session_is_not_committed_and_retry_recovers(database):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    original = {key:list(rows) for key,rows in source.bars.items()}
    source.bars = {key:rows[:1] for key,rows in source.bars.items()}
    runner = service(database, source)
    with pytest.raises(RefreshError, match='INCOMPLETE_MARKET_DATA'):
        runner.run(symbol='RB', exchange='SHFE')
    repo = database['market_repository']
    instrument = repo.resolve_instrument(symbol='RB', exchange='SHFE')
    assert repo.load_curve_snapshots(instrument_id=instrument.instrument_id, as_of=NOW, limit=20) == ()
    source.bars = original
    result = runner.run(symbol='RB', exchange='SHFE')
    assert result['refresh']['latest_session'] == '2026-09-02'
    assert len(repo.load_curve_snapshots(instrument_id=instrument.instrument_id, as_of=NOW, limit=20)) == 2
    contract = repo.resolve_contract(symbol='RB', exchange='SHFE', contract_code='RB2701')
    assert len(repo.load_contract_bars(contract_id=contract.contract_id, as_of=NOW, limit=20)) == 2

@pytest.mark.parametrize('failure', ['calendar','provider'])
def test_refresh_fails_closed_and_sanitizes_errors(database, failure):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    source.omit_calendar = failure == 'calendar'
    source.error = failure == 'provider'
    with pytest.raises(RefreshError) as caught:
        service(database, source).run(symbol='RB', exchange='SHFE')
    assert 'secret-provider-token' not in str(caught.value)
    assert caught.value.status_code == 503

def test_refresh_correction_changes_input_hash(database):
    source = CalendarSource()
    runner = service(database, source)
    first = runner.run(symbol='RB', exchange='SHFE')
    source.bars['RB2701.SHF'][1] = _bar('RB2701.SHF','20260902',3300,3301,908468,1402797,2869314.246)
    second = runner.run(symbol='RB', exchange='SHFE')
    assert second['refresh']['bars_revised'] == 1
    assert second['analysis']['input_data_hash'] != first['analysis']['input_data_hash']

def test_mid_provider_failure_retry_recovers_all_contracts(database):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    original = source.fetch_daily_bars
    def broken(**kwargs):
        if kwargs['ts_code'] == 'RB2701.SHF':
            raise RuntimeError('provider-secret')
        return original(**kwargs)
    source.fetch_daily_bars = broken
    runner = service(database, source)
    with pytest.raises(RefreshError):
        runner.run(symbol='RB', exchange='SHFE')
    source.fetch_daily_bars = original
    result = runner.run(symbol='RB', exchange='SHFE')
    assert result['refresh']['latest_session'] == '2026-09-02'
    repo = database['market_repository']
    contract = repo.resolve_contract(symbol='RB', exchange='SHFE', contract_code='RB2610')
    assert len(repo.load_contract_bars(contract_id=contract.contract_id, as_of=NOW, limit=20)) == 2


def test_missing_previously_liquid_target_contract_fails_closed(database):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    runner = service(database, source)
    runner.run(symbol='RB', exchange='SHFE')
    source.bars['RB2701.SHF'] = source.bars['RB2701.SHF'][:1]
    with pytest.raises(RefreshError, match='INCOMPLETE_MARKET_DATA'):
        runner.run(symbol='RB', exchange='SHFE')


def test_missing_token_never_uses_cached_analysis(database, monkeypatch):
    from dragonboat_ai.futures_agent.application.refresh import RefreshAndAnalyzeService, RefreshError
    monkeypatch.delenv('TUSHARE_TOKEN', raising=False)
    runner = RefreshAndAnalyzeService(database['market_repository'], None, clock=lambda: NOW)
    with pytest.raises(RefreshError, match='SOURCE_AUTH_ERROR'):
        runner.run(symbol='RB', exchange='SHFE')


def test_concurrent_refresh_is_rejected_without_queue(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    original = source.fetch_trade_cal
    entered, release = Event(), Event()
    def blocked(**kwargs):
        entered.set()
        assert release.wait(5)
        return original(**kwargs)
    source.fetch_trade_cal = blocked
    runner = service(database, source)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runner.run, symbol='RB', exchange='SHFE')
        assert entered.wait(5)
        try:
            with pytest.raises(RefreshError, match='REFRESH_IN_PROGRESS') as caught:
                runner.run(symbol='RB', exchange='SHFE')
            assert caught.value.status_code == 409
        finally:
            release.set()
        assert first.result()['refresh']['status'] == 'updated'

def test_bootstrap_rejects_empty_active_contract_response(database):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    source.bars['RB2705.SHF'] = []
    with pytest.raises(RefreshError, match='INCOMPLETE_MARKET_DATA'):
        service(database, source).run(symbol='RB', exchange='SHFE')

def test_continuous_index_metadata_does_not_block_delivery_refresh(database):
    source = CalendarSource()
    source.contracts.extend([
        dict(ts_code=f'{code}.SHF', symbol=code, fut_code='RB', exchange='SHFE',
             list_date=None, delist_date=None, d_month=None)
        for code in ['RB', 'RBL']
    ])
    result = service(database, source).run(symbol='RB', exchange='SHFE')
    assert result['refresh']['status'] == 'updated'
    assert result['refresh']['latest_session'] == '2026-09-02'
    assert all(request[0] not in {'RB.SHF', 'RBL.SHF'} for request in source.bar_requests)


def test_dated_delivery_contract_without_expiry_still_fails(database):
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    source = CalendarSource()
    source.contracts.append(dict(ts_code='RB2709.SHF', symbol='RB2709', fut_code='RB',
                                 exchange='SHFE', list_date='20260901', delist_date=None))
    with pytest.raises(RefreshError, match='INCOMPLETE_MARKET_DATA'):
        service(database, source).run(symbol='RB', exchange='SHFE')


def test_partial_ohlc_commits_without_synthetic_prices(database):
    source = CalendarSource()
    source.bars['RB2701.SHF'][0].update(open=None, high=None, low=None)
    result = service(database, source).run(symbol='RB', exchange='SHFE')
    assert result['refresh']['bars_partial_ohlc'] == 1
    repo = database['market_repository']
    contract = repo.resolve_contract(symbol='RB', exchange='SHFE', contract_code='RB2701')
    bars = repo.load_contract_bars(contract_id=contract.contract_id, as_of=NOW, limit=20)
    assert bars[0].high is None and bars[0].open is None
    assert bars[0].settlement is not None


def test_atr_requires_complete_window_but_ignores_older_gaps():
    from dataclasses import replace
    from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import map_fut_daily_bar
    from dragonboat_ai.futures_agent.features.statistics import average_true_range_pct
    from tests.unit.test_tushare_mapper import RB2701_DAILY
    bar = map_fut_daily_bar(RB2701_DAILY, contract_id=1)
    bars = [replace(bar, trading_date=date(2026, 1, 1)+timedelta(days=i)) for i in range(30)]
    bars[0] = replace(bars[0], high=None)
    assert average_true_range_pct(bars, 20) is not None
    bars[-2] = replace(bars[-2], high=None)
    assert average_true_range_pct(bars, 20) is None


def test_corrected_null_prices_do_not_deduplicate_against_old_synthetic_fill(database):
    from dataclasses import replace
    from decimal import Decimal
    from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import map_fut_daily_bar
    source = CalendarSource()
    runner = service(database, source)
    runner.run(symbol='RB', exchange='SHFE')
    repo = database['market_repository']
    ref = repo.resolve_contract(symbol='RB', exchange='SHFE', contract_code='RB2701')
    row = dict(source.bars['RB2701.SHF'][0], high=None)
    partial = map_fut_daily_bar(row, contract_id=ref.contract_id)
    synthetic = replace(partial, high=Decimal('3400'))
    repo.ingest_daily_bar(synthetic, correction_available_at=NOW)
    assert repo.ingest_daily_bar(partial, correction_available_at=NOW) == 'revised'
