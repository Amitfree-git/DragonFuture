"""Persist observations against the original analysis; never rewrite its verdict."""
from __future__ import annotations

from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, text

from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis
from dragonboat_ai.futures_agent.infrastructure.database.models import (
    FutAnalysisRunORM, FutInvalidationStateORM,
)
from dragonboat_ai.futures_agent.invalidation.state import InvalidationStateMachine, StreakState


def record_analysis_observation(factory, current: FuturesMarketAnalysis) -> None:
    observed_at = current.request.as_of.astimezone(timezone.utc).replace(tzinfo=None)
    with factory() as session:
        session.execute(text('BEGIN IMMEDIATE'))
        try:
            persisted = session.get(FutAnalysisRunORM, current.analysis_id)
            if persisted is None:
                raise ValueError("observation analysis must be persisted first")
            originals = session.scalars(select(FutAnalysisRunORM).where(
                FutAnalysisRunORM.symbol == current.request.symbol,
                FutAnalysisRunORM.exchange == persisted.exchange,
                FutAnalysisRunORM.horizon == current.request.horizon.value,
                FutAnalysisRunORM.as_of <= observed_at,
            )).all()
            for row in originals:
                original = FuturesMarketAnalysis.model_validate(row.core_result_json)
                for rule in original.invalidation_conditions:
                    metric = current.metrics.get(rule.metric_name)
                    origin_metric = original.metrics.get(rule.metric_name)
                    # Streaks count actual data sessions, never request dates.
                    day = metric.window_end if metric else None
                    original_day = origin_metric.window_end if origin_metric else None
                    if day is None or original_day is None or day < original_day:
                        continue
                    rows = session.scalars(select(FutInvalidationStateORM).where(
                        FutInvalidationStateORM.analysis_id == original.analysis_id,
                        FutInvalidationStateORM.condition_id == rule.condition_id,
                    ).order_by(FutInvalidationStateORM.evaluated_at.desc(), FutInvalidationStateORM.state_id.desc())).all()
                    history = [item.state_json for item in rows]
                    latest = history[0] if history else None
                    if latest and latest['session_date'] > day.isoformat():
                        continue
                    if latest and latest['session_date'] == day.isoformat() and latest['input_data_hash'] == current.input_data_hash:
                        continue
                    # A same-session revision is recomputed from the prior
                    # session and appended. It never advances the streak twice.
                    prior = next((item for item in history if item['session_date'] < day.isoformat()), None)
                    value = getattr(metric, rule.value_field) if metric.status.value in {'ok','partial'} else None
                    if current.selected_contract != original.selected_contract or current.data_quality.blocking_issues:
                        value = None
                    state = StreakState()
                    if prior:
                        state = StreakState(last_session=date.fromisoformat(prior['session_date']),streak=prior['streak'],last_value=prior['value'],triggered=prior['triggered'],status=prior['status'])
                    if day == original_day:
                        state = StreakState(last_session=day,last_value=value,status='active')
                    elif state.status != 'invalidated':
                        expected = day-timedelta(days=1)
                        while expected.weekday() >= 5:
                            expected -= timedelta(days=1)
                        if prior and state.last_session != expected:
                            state.streak = 0
                            state.last_value = None
                        machine = InvalidationStateMachine()
                        machine._states[rule.condition_id] = state
                        state = machine.observe(condition_id=rule.condition_id,session_date=day,value=value,operator=rule.operator,threshold=rule.threshold,consecutive_bars=rule.consecutive_bars)
                    payload={'session_date':day.isoformat(),'status':state.status,'streak':state.streak,'value':value,'triggered':state.triggered,'input_data_hash':current.input_data_hash,'observation_analysis_id':current.analysis_id,'rule_version':'invalidation_v2','calendar_policy':'weekday_conservative'}
                    session.add(FutInvalidationStateORM(analysis_id=original.analysis_id,condition_id=rule.condition_id,evaluated_at=observed_at,triggered=state.triggered,observed_value=value,state_json=payload))
            session.commit()
        except Exception:
            session.rollback()
            raise


def read_invalidation(factory, original: FuturesMarketAnalysis) -> dict:
    conditions=[]
    with factory() as session:
        for rule in original.invalidation_conditions:
            row=session.scalar(select(FutInvalidationStateORM).where(FutInvalidationStateORM.analysis_id==original.analysis_id,FutInvalidationStateORM.condition_id==rule.condition_id).order_by(FutInvalidationStateORM.evaluated_at.desc(),FutInvalidationStateORM.state_id.desc()).limit(1))
            conditions.append({'condition':rule.model_dump(mode='json'),'state':row.state_json if row else {'status':'not_evaluated'}})
    statuses={x['state']['status'] for x in conditions}
    status=next((s for s in ('invalidated','unknown','not_evaluated','warning') if s in statuses),'active')
    return {'analysis_id':original.analysis_id,'status':status,'conditions':conditions,'evaluation_policy':'on_analysis_creation','production_ready':False}
