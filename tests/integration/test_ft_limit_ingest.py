from datetime import timedelta
from decimal import Decimal
import pytest
from tests.integration.test_refresh_service import CalendarSource, service, NOW
from dragonboat_ai.futures_agent.application.refresh import RefreshError

class LimitSource(CalendarSource):
    def __init__(self):
        super().__init__()
        self.limits = {code: [dict(ts_code=code, trade_date=row['trade_date'], up_limit=3500, down_limit=2800) for row in rows] for code, rows in self.bars.items()}
    def fetch_price_limits(self, *, ts_code, start, end):
        return self.limits.get(ts_code, [])

def test_limits_join_revision_removal_and_asof(database):
    source = LimitSource()
    repo = database['market_repository']
    # First import without limits, then add them at a later receipt time.
    original = source.limits
    source.limits = {}
    runner = service(database, source)
    first = runner.run(symbol='RB', exchange='SHFE')
    assert 'unknown_price_limit_risk' in first['analysis']['opportunity']['hard_gate_reasons']
    source.limits = original
    runner.clock = lambda: NOW + timedelta(minutes=1)
    second = runner.run(symbol='RB', exchange='SHFE')
    assert second['refresh']['bars_with_price_limits'] == 6
    assert second['refresh']['bars_revised'] == 6
    assert 'unknown_price_limit_risk' not in second['analysis']['opportunity']['hard_gate_reasons']
    ref = repo.resolve_contract(symbol='RB', exchange='SHFE', contract_code='RB2701')
    assert repo.load_contract_bars(contract_id=ref.contract_id, as_of=NOW, limit=10)[-1].upper_limit is None
    latest = repo.load_contract_bars(contract_id=ref.contract_id, as_of=runner.clock(), limit=10)[-1]
    assert latest.upper_limit == Decimal('3500')
    repeat = runner.run(symbol='RB', exchange='SHFE')
    assert repeat['refresh']['bars_revised'] == 0
    assert repeat['analysis']['input_data_hash'] == second['analysis']['input_data_hash']
    source.limits['RB2701.SHF'][-1]['up_limit'] = 3158
    third = runner.run(symbol='RB', exchange='SHFE')
    assert third['refresh']['bars_revised'] == 1
    assert 'price_limit_risk' in third['analysis']['opportunity']['hard_gate_reasons']
    source.limits = {}
    fourth = runner.run(symbol='RB', exchange='SHFE')
    assert fourth['refresh']['bars_missing_price_limits'] == 6
    assert 'unknown_price_limit_risk' in fourth['analysis']['opportunity']['hard_gate_reasons']

@pytest.mark.parametrize('bad', [
    {'ts_code':'M2701.DCE'}, {'trade_date':'20270901'},
    {'up_limit':float('nan')}, {'down_limit':-1}, {'down_limit':3600},
])
def test_invalid_limit_response_fails_closed(database, bad):
    source = LimitSource()
    source.limits['RB2701.SHF'][0].update(bad)
    with pytest.raises(RefreshError):
        service(database, source).run(symbol='RB', exchange='SHFE')


def test_duplicate_limit_key_fails_closed(database):
    source=LimitSource()
    source.limits['RB2701.SHF'].append(dict(source.limits['RB2701.SHF'][0]))
    with pytest.raises(RefreshError):
        service(database, source).run(symbol='RB', exchange='SHFE')


def test_partial_limit_pair_does_not_fill(database):
    source=LimitSource()
    source.limits['RB2701.SHF'][-1]['up_limit']=None
    result=service(database,source).run(symbol='RB',exchange='SHFE')
    assert result['refresh']['bars_missing_price_limits']==1
    assert 'unknown_price_limit_risk' in result['analysis']['opportunity']['hard_gate_reasons']


def test_first_import_limits_not_visible_before_receipt(database):
    from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
    source=LimitSource();repo=database['market_repository']
    TushareMarketIngestor(repo,source,clock=lambda:NOW).ingest(product='RB',exchange='SHFE',start='20260901',end='20260902')
    ref=repo.resolve_contract(symbol='RB',exchange='SHFE',contract_code='RB2701')
    assert repo.load_contract_bars(contract_id=ref.contract_id,as_of=NOW-timedelta(seconds=1),limit=10)==()
