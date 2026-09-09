from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.contracts.mapping_pipeline import build_mapping_and_continuous
from dragonboat_ai.futures_agent.domain.exceptions import InsufficientDataError
from dragonboat_ai.futures_agent.domain.market_data import CurvePoint, CurveSnapshot
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest

TZ = ZoneInfo('Asia/Shanghai')
def at(day):
    return datetime.combine(day, datetime.min.time(), TZ).replace(hour=16)

def seed(repo, *, missing=False):
    iid = repo.get_or_create_instrument(exchange='SHFE', symbol='RB')
    refs = [repo.get_or_create_contract(instrument_id=iid, contract_code=c, expiry_date=date(2027, m, 15)) for c,m in [('RB2701',1),('RB2705',5)]]
    days = [date(2026,9,1)+timedelta(days=i) for i in range(4)]
    for i, day in enumerate(days):
        if missing and i == 2:
            continue
        points = tuple(CurvePoint(r.contract_id,r.contract_code,r.expiry_date,150,Decimal(str(p)),v,v) for r,p,v in zip(refs,[100+i,200+i],([300,100] if i==0 else [100,300])))
        repo.add_curve_snapshot(CurveSnapshot(f'curve-{i}',iid,'SHFE','RB',day,at(day),at(day),points,'fixture',f'hash-{i}'))
    return iid, days, refs

def build(repo, day):
    return build_mapping_and_continuous(repo, symbol='RB', exchange='SHFE',as_of=at(day))

def bars(repo,iid,day):
    return repo.load_continuous_bars(instrument_id=iid,as_of=at(day))

@pytest.mark.integration
def test_full_build_does_not_expose_future_adjustment(database):
    repo=database['market_repository']; iid,days,_=seed(repo)
    build(repo,days[-1])
    historical=bars(repo,iid,days[1])
    assert [b.adjusted_settlement for b in historical] == [Decimal(100),Decimal(101)]
    assert all(b.series_snapshot_id for b in historical)

@pytest.mark.integration
def test_incremental_build_matches_full_and_research_ignores_roll_gap(database):
    repo=database['market_repository']; iid,days,_=seed(repo)
    build(repo,days[2]); before=bars(repo,iid,days[2]); build(repo,days[3])
    after=bars(repo,iid,days[3])
    assert [b.adjusted_settlement for b in after] == [Decimal(200),Decimal(201),Decimal(202),Decimal(203)]
    assert [b.research_index for b in after] == [Decimal(100),Decimal(101),Decimal(102),Decimal(102) * (Decimal(203) / Decimal(202))]
    assert bars(repo,iid,days[2]) == before

@pytest.mark.integration
def test_pipeline_missing_session_breaks_confirmation(database):
    repo=database['market_repository']; iid,days,refs=seed(repo,missing=True)
    build(repo,days[-1])
    mapping=repo.load_effective_mapping(instrument_id=iid,session_date=date(2026,9,7),as_of=at(days[-1]))
    assert mapping.contract.contract_code == refs[0].contract_code

@pytest.mark.integration
@pytest.mark.parametrize("blocked_effective", [date(2026,9,2), None])
def test_blocked_mapping_cannot_fall_back_to_an_old_contract(database, blocked_effective):
    repo=database['market_repository']; iid,days,refs=seed(repo)
    for i in (0,1):
        repo.save_contract_mapping(mapping_id=f'map-{i}',instrument_id=iid,to_contract_id=refs[0].contract_id if i==0 else None,decision_date=days[i],effective_session=days[i] if i==0 else blocked_effective,action='keep' if i==0 else 'blocked',available_at=at(days[i]))
    with pytest.raises(InsufficientDataError, match='blocked'):
        SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=at(days[1])))

@pytest.mark.integration
def test_future_curve_revision_cannot_rewrite_historical_series(database):
    repo=database['market_repository']; iid,days,_=seed(repo); build(repo,days[-1]); before=bars(repo,iid,days[1])
    original=repo.load_curve_snapshots(instrument_id=iid,as_of=at(days[1]))[-1]
    revised=replace(original,snapshot_id='revised',available_at=at(date(2026,9,8)),input_hash='revised-hash',points=tuple(replace(p,settlement=p.settlement*2) for p in original.points))
    repo.add_curve_snapshot(revised,revision_no=2); build(repo,date(2026,9,8))
    assert bars(repo,iid,days[1]) == before
    assert bars(repo,iid,date(2026,9,8))[1].raw_settlement == Decimal(202)

@pytest.mark.integration
def test_features_use_raw_return_index_and_selected_contract_entry_scale(database):
    from tests.support import seed_reference_market
    from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    context=SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    engine=ReferenceFeatureEngine(); original=engine.compute(context)
    rebased=replace(context,continuous_bars=tuple(replace(b,adjusted_settlement=b.adjusted_settlement+Decimal(10000)) for b in context.continuous_bars))
    other=engine.compute(rebased)
    assert original['return_20d'].value == other['return_20d'].value
    assert original['extension_atr'].value == other['extension_atr'].value
    assert original['return_20d'].source == 'research_index'
    assert original['extension_atr'].source == 'selected_contract'

@pytest.mark.integration
def test_later_liquidity_revision_has_its_own_mapping_and_roll_timeline(database):
    repo=database['market_repository']; iid,days,refs=seed(repo); build(repo,days[-1])
    prior=repo.load_curve_snapshots(instrument_id=iid,as_of=at(days[1]))[-1]
    later=date(2026,9,8)
    revised=replace(prior,snapshot_id='liquidity-revision',available_at=at(later),input_hash='liquidity-revision',points=tuple(replace(p,volume=500 if i==0 else 100,open_interest=500 if i==0 else 100) for i,p in enumerate(prior.points)))
    repo.add_curve_snapshot(revised,revision_no=2); build(repo,later)
    assert repo.latest_roll_date(instrument_id=iid,as_of=at(later)) is None
    assert repo.latest_roll_date(instrument_id=iid,as_of=at(days[-1])) == days[-1]
    selected=repo.load_effective_mapping(instrument_id=iid,session_date=days[-1],as_of=at(later))
    assert selected.contract.contract_code == refs[0].contract_code

@pytest.mark.integration
def test_snapshot_payload_is_immutable_even_if_caller_reuses_hash(database):
    repo=database['market_repository']; iid,_,_=seed(repo)
    kwargs=dict(snapshot_id='immutable-test',instrument_id=iid,series_type='back_adjusted',calculation_version='continuous_v1',input_hash='same',available_at=at(date(2026,9,4)))
    repo.save_series_snapshot(**kwargs,payload={'points':[1]})
    with pytest.raises(ValueError,match='immutable'):
        repo.save_series_snapshot(**kwargs,payload={'points':[2]})

@pytest.mark.integration
def test_context_without_persisted_mapping_also_breaks_confirmation_at_gap(database):
    repo=database['market_repository']; _,days,refs=seed(repo,missing=True)
    context=SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=at(days[-1])))
    assert context.selected_contract == refs[0].contract_code

@pytest.mark.integration
def test_context_reads_one_snapshot_when_writer_commits_between_queries(database, monkeypatch):
    from tests.support import seed_reference_market
    from dragonboat_ai.futures_agent.infrastructure.database.repositories import SqlAlchemyMarketDataRepository
    from sqlalchemy import event
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    # Every read in the builder must reuse a single database connection/transaction.
    connections=set()
    def before_execute(conn, cursor, statement, *args):
        if str(statement).lstrip().upper().startswith('SELECT'):
            connections.add(id(conn))
    event.listen(database['engine'],'before_cursor_execute',before_execute)
    SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    assert len(connections) == 1

@pytest.mark.integration
def test_missing_research_lineage_fails_closed(database):
    from tests.support import seed_reference_market
    from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    context=SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    context=replace(context,continuous_bars=tuple(replace(b,research_index=None,series_snapshot_id=None) for b in context.continuous_bars))
    assert ReferenceFeatureEngine().compute(context)['return_20d'].value is None

@pytest.mark.integration
def test_contract_feature_observation_time_tracks_actual_contract_bar(database):
    from tests.support import seed_reference_market
    from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    context=SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    context=replace(context,contract_bars=tuple(replace(b,trading_date=b.trading_date-timedelta(days=7)) for b in context.contract_bars))
    metrics=ReferenceFeatureEngine().compute(context)
    for name in ('settlement_vs_ma60','extension_atr','price_limit_proximity_risk','contract_return_5d'):
        assert metrics[name].observation_time.date() == context.contract_bars[-1].trading_date
        assert metrics[name].window_end == context.contract_bars[-1].trading_date
        assert metrics[name].window_start <= metrics[name].window_end

@pytest.mark.integration
def test_read_snapshot_excludes_a_revision_committed_during_context_build(database):
    from tests.support import seed_reference_market
    from sqlalchemy import event
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    request=AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of'])
    original=SqlAlchemyMarketContextBuilder(repo).build(request)
    latest=original.contract_bars[-1]
    revised=replace(latest,settlement=latest.settlement+Decimal(1),revision_no=latest.revision_no+1,payload_hash='concurrent-change')
    wrote=False
    def insert_revision(conn,cursor,statement,*args):
        nonlocal wrote
        if not wrote and 'fut_curve_snapshot' in statement:
            wrote=True
            repo.add_daily_bar(revised)
    event.listen(database['engine'],'after_cursor_execute',insert_revision)
    try:
        during=SqlAlchemyMarketContextBuilder(repo).build(request)
    finally:
        event.remove(database['engine'],'after_cursor_execute',insert_revision)
    assert wrote
    assert during.input_data_hash == original.input_data_hash
    after=SqlAlchemyMarketContextBuilder(repo).build(request)
    assert after.contract_bars[-1].settlement == revised.settlement
    assert after.input_data_hash != original.input_data_hash

@pytest.mark.integration
def test_metric_availability_includes_all_normalization_and_curve_dependencies(database):
    from tests.support import seed_reference_market
    from dragonboat_ai.futures_agent.features.engine import ReferenceFeatureEngine
    repo=database['market_repository']; fixture=seed_reference_market(repo)
    context=SqlAlchemyMarketContextBuilder(repo).build(AnalysisRequest(symbol='RB',exchange='SHFE',as_of=fixture['as_of']))
    cutoff=context.request.as_of
    old=cutoff-timedelta(hours=2); research_time=cutoff-timedelta(hours=1)
    curves=list(context.historical_curves); curves[0]=replace(curves[0],available_at=cutoff)
    context=replace(context,contract_bars=tuple(replace(b,available_at=old) for b in context.contract_bars),continuous_bars=tuple(replace(b,available_at=research_time) for b in context.continuous_bars),historical_curves=tuple(curves))
    metrics=ReferenceFeatureEngine().compute(context)
    assert metrics['curve_slope'].available_at == cutoff
    assert metrics['liquidity_quality_score'].available_at == max(old,context.current_curve.available_at)
    assert metrics['settlement_vs_ma60'].available_at == research_time
    assert metrics['contract_return_5d'].available_at == research_time

@pytest.mark.integration
def test_context_rejects_new_curve_revision_until_causal_series_rebuilt(database):
    repo=database['market_repository']; iid,days,_=seed(repo); build(repo,days[-1])
    original=repo.load_curve_snapshots(instrument_id=iid,as_of=at(days[-1]))[-1]
    later=date(2026,9,8)
    revision=replace(original,snapshot_id='pending-series-rebuild',input_hash='pending-series-rebuild',available_at=at(later),points=tuple(replace(p,settlement=p.settlement+1) for p in original.points))
    repo.add_curve_snapshot(revision,revision_no=2)
    request=AnalysisRequest(symbol='RB',exchange='SHFE',as_of=at(later))
    with pytest.raises(InsufficientDataError,match='series_rebuild_required'):
        SqlAlchemyMarketContextBuilder(repo).build(request)
    build(repo,later)
    context=SqlAlchemyMarketContextBuilder(repo).build(request)
    assert context.series_snapshot_id == context.continuous_bars[-1].series_snapshot_id
    assert context.current_curve.snapshot_id == revision.snapshot_id
