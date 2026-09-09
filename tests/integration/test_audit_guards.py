from dataclasses import replace
from datetime import date, timedelta

from fastapi.testclient import TestClient

from dragonboat_ai.futures_agent.api.app import create_app
from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.scoring.data_quality import DataQualityEvaluator
from dragonboat_ai.futures_agent.research.replay import walk_forward_splits, purge_overlapping_labels
from dragonboat_ai.futures_agent.invalidation.state import InvalidationStateMachine
from tests.support import seed_reference_market
from tests.unit.test_missing_critical_risk import metric, _strong_long_inputs


def test_absent_limit_key_blocks_candidate():
    metrics = {n: metric(n,v) for n,v in [('volatility_percentile',40),('roll_risk_score',0),('liquidity_quality_score',90),('extension_atr',0.4),('rsi_14',55)]}
    risk, opportunity = _strong_long_inputs(metrics)
    assert risk.hard_gate_triggered
    assert opportunity.action.value == 'no_trade'


def test_stale_continuous_not_masked_by_fresh_contract(database):
    fixture = seed_reference_market(database['market_repository'])
    context = SqlAlchemyMarketContextBuilder(database['market_repository']).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    stale = replace(context, continuous_bars=tuple(replace(b,trading_date=b.trading_date-timedelta(days=30),available_at=b.available_at-timedelta(days=30)) for b in context.continuous_bars))
    quality = DataQualityEvaluator().assess(stale)
    assert 'continuous_series' in quality.stale_sources
    assert quality.blocking_issues


def test_core_is_committed_before_narrative(database):
    fixture = seed_reference_market(database['market_repository'])
    repo = database['analysis_repository']
    persisted = []
    class Probe:
        def generate(self, core):
            persisted.append(repo.get(core.analysis_id) is not None)
            raise TimeoutError('probe')
    analyst = FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=repo,narrative_generator=Probe())
    result = analyst.analyze(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    assert persisted == [True]
    assert repo.get(result.analysis_id) is not None


def test_empty_database_is_not_ready(tmp_path):
    with TestClient(create_app(f'sqlite:///{tmp_path}/empty.db')) as client:
        assert client.get('/api/v1/futures/ready').status_code == 503


def test_walkforward_purges_training_label_end():
    days = [date(2026,1,1)+timedelta(days=i) for i in range(80)]
    train,val,test = walk_forward_splits(days,train_days=10,validate_days=10,test_days=10,embargo_days=5,max_label_horizon=5)[0]
    assert days.index(train[-1])+6 < days.index(val[0])
    assert days.index(val[-1])+6 < days.index(test[0])


def test_missing_observation_clears_invalidation_streak():
    m = InvalidationStateMachine()
    for day,value in [(1,-1),(2,None),(3,-1)]:
        result = m.observe(condition_id='a',session_date=date(2026,9,day),value=value,operator='lt',threshold=0)
    assert result.streak == 1


def test_purge_uses_actual_label_end_and_boundary():
    days = [date(2026,1,1)+timedelta(days=i) for i in range(40)]
    kept = purge_overlapping_labels(days[:10],horizon=5,ordered_sessions=days,cutoff=days[10])
    assert kept == days[:4]


def test_source_mode_and_code_identity_are_explicit(database):
    fixture = seed_reference_market(database['market_repository'])
    analyst = FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=database['analysis_repository'])
    result = analyst.analyze(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    assert result.versions.code_commit
    assert result.model_dump()['production_ready'] is False
    assert result.model_dump()['data_mode'] in {'synthetic','final_only','estimated'}


def test_shadow_rerun_preserves_failure_history(database):
    from dragonboat_ai.futures_agent.operations.shadow import SqlShadowStore, ShadowObservation
    from dragonboat_ai.futures_agent.infrastructure.database.models import FutShadowRunORM
    from sqlalchemy import select
    observation = ShadowObservation(session_date=date(2026,9,4),exchange='SHFE',symbol='RB',horizon='swing',watermark_status='missing',input_data_hash=None,core_result_hash=None,opportunity_action=None,hard_gate=True,blocking_reasons=('network',),gap=True,candidate_emitted=False,fault='network')
    store=SqlShadowStore(database['session_factory'])
    store.save(observation)
    store.save(replace(observation,gap=False,blocking_reasons=(),watermark_status='ready'))
    with database['session_factory']() as session:
        rows=session.scalars(select(FutShadowRunORM)).all()
        assert len(rows)==2
        assert any(r.gap for r in rows)


def test_invalidation_endpoint_tracks_original_rules(tmp_path):
    app=create_app(f'sqlite:///{tmp_path}/states.db')
    fixture=seed_reference_market(app.state.market_repository)
    with TestClient(app) as client:
        response=client.post('/api/v1/futures/analyses',json={'symbol':'RB','exchange':'SHFE','as_of':fixture['as_of'].isoformat(),'include_narrative':False})
        assert response.status_code==200
        aid=response.json()['analysis_id']
        states=client.get(f'/api/v1/futures/analyses/{aid}/invalidation')
        assert states.status_code==200
        assert states.json()['analysis_id']==aid
        assert states.json()['status']=='active'
        assert len(states.json()['conditions'])==len(response.json()['invalidation_conditions'])


def test_ingest_preserves_receive_time_and_recoverable_raw_archive(database):
    from datetime import datetime, timezone
    from pathlib import Path
    from sqlalchemy import text
    from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
    from tests.integration.test_tushare_ingest import _source
    clock=datetime(2026,9,5,8,tzinfo=timezone.utc)
    report=TushareMarketIngestor(database['market_repository'],_source(),clock=lambda:clock).ingest(product='RB',exchange='SHFE',start='20260901',end='20260902')
    with database['engine'].connect() as conn:
        received=conn.scalar(text('select received_at from fut_bar_daily limit 1'))
        uris=conn.execute(text('select storage_uri from fut_raw_archive')).scalars().all()
    assert str(received).startswith('2026-09-05 08:00:00')
    assert uris and all(uri.startswith('file://') for uri in uris)
    assert all(Path(uri.removeprefix('file://')).is_file() for uri in uris)


def test_blocking_narrative_has_bounded_wait(database):
    import threading, time
    fixture=seed_reference_market(database['market_repository'])
    release=threading.Event()
    class Hanging:
        def generate(self, core):
            release.wait(2)
            raise TimeoutError('test release')
    analyst=FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=database['analysis_repository'],narrative_generator=Hanging())
    analyst.narrative_timeout_seconds=0.02
    start=time.monotonic()
    try:
        result=analyst.analyze(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
        assert time.monotonic()-start < 1
        assert result.narrative is not None
    finally:
        release.set()


def test_next_session_label_rejects_internal_missing_index():
    from decimal import Decimal
    from dragonboat_ai.futures_agent.research.replay import next_session_label
    days=[date(2026,9,1)+timedelta(days=i) for i in range(5)]
    index={day:Decimal(100+i) for i,day in enumerate(days)}
    index[days[2]]=None
    assert next_session_label(index,days,days[0],3) is None


def test_invalidation_does_not_count_repeated_old_bar(database):
    from dragonboat_ai.futures_agent.invalidation.service import record_analysis_observation,read_invalidation
    fixture=seed_reference_market(database['market_repository'])
    analyst=FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=database['analysis_repository'])
    original=analyst.analyze(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of'],include_narrative=False))
    metrics={k:v.model_copy(update={'value':-1.0,'normalized_score':-80.0}) for k,v in original.metrics.items()}
    for offset in (3,4):
        changed=original.model_copy(update={'request':original.request.model_copy(update={'as_of':original.request.as_of+timedelta(days=offset)}),'metrics':metrics})
        record_analysis_observation(database['session_factory'],changed)
    states=read_invalidation(database['session_factory'],original)
    assert states['status']!='invalidated'


def test_invalidation_resolves_optional_exchange(database):
    from dragonboat_ai.futures_agent.invalidation.service import read_invalidation
    fixture=seed_reference_market(database['market_repository'])
    analyst=FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=database['analysis_repository'])
    original=analyst.analyze(AnalysisRequest(symbol='RB',as_of=fixture['as_of'],include_narrative=False))
    assert read_invalidation(database['session_factory'],original)['status']=='active'


def test_two_simultaneous_requests_are_idempotent(database):
    from concurrent.futures import ThreadPoolExecutor
    fixture=seed_reference_market(database['market_repository'])
    analyst=FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(database['market_repository']),analysis_repository=database['analysis_repository'])
    request=AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of'],include_narrative=False)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(lambda _:analyst.analyze(request),range(2)))
    assert results[0].analysis_id==results[1].analysis_id


def test_equivalent_timezones_have_same_request_identity():
    from datetime import datetime,timezone
    from zoneinfo import ZoneInfo
    instant=datetime(2026,9,4,18,tzinfo=timezone.utc)
    a=AnalysisRequest(symbol='RB',as_of=instant)
    b=AnalysisRequest(symbol='RB',as_of=instant.astimezone(ZoneInfo('Asia/Shanghai')))
    assert FuturesMarketAnalyst._request_hash(a)==FuturesMarketAnalyst._request_hash(b)


def test_default_walkforward_protects_sixty_session_labels():
    days=[date(2026,1,1)+timedelta(days=i) for i in range(220)]
    train,val,test=walk_forward_splits(days,train_days=10,validate_days=10,test_days=10,embargo_days=0)[0]
    assert days.index(train[-1])+61 < days.index(val[0])
    assert days.index(val[-1])+61 < days.index(test[0])


def test_vintage_validation_includes_dependencies_older_than_400(database,monkeypatch):
    from types import SimpleNamespace
    from datetime import datetime,timezone
    import pytest
    from dragonboat_ai.futures_agent.domain.exceptions import InsufficientDataError
    repo=database['market_repository']
    stamp=datetime(2026,9,4,tzinfo=timezone.utc)
    curves=tuple(SimpleNamespace(snapshot_id=str(i),input_hash='original',available_at=stamp) for i in range(401))
    expected=[[c.snapshot_id,c.input_hash,c.available_at.isoformat()] for c in curves]
    changed=(SimpleNamespace(snapshot_id='0',input_hash='revised',available_at=stamp),)+curves[1:]
    monkeypatch.setattr(repo,'_visible_series_snapshot',lambda **kwargs:SimpleNamespace(payload_json={'inputs':expected}))
    monkeypatch.setattr(repo,'load_curve_snapshots',lambda **kwargs:changed)
    with pytest.raises(InsufficientDataError,match='series_rebuild_required'):
        repo.validate_series_inputs(instrument_id=1,as_of=stamp,curves=changed[-400:])
