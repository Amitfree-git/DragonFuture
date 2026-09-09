"""Replay stored research snapshots. This is labelled research, not strategy PnL."""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.infrastructure.database.repositories import SqlAlchemyAnalysisRepository, SqlAlchemyMarketDataRepository
from dragonboat_ai.futures_agent.infrastructure.database.session import create_session_factory, create_sqlite_engine
from dragonboat_ai.futures_agent.research.evaluation import summarize_direction_buckets
from dragonboat_ai.futures_agent.research.replay import ReplayRecord, next_session_label
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.domain.exceptions import FuturesAgentError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',required=True,help='Use an isolated migrated copy; analysis records are appended')
    parser.add_argument('--product',default='RB')
    parser.add_argument('--exchange',default='SHFE')
    parser.add_argument('--end',required=True,help='YYYY-MM-DD last data session')
    parser.add_argument('--days',type=int,default=60)
    args=parser.parse_args()
    if not 1<=args.days<=2000:
        parser.error('--days must be between 1 and 2000')
    as_of=datetime.fromisoformat(args.end+'T16:00:00').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    engine=create_sqlite_engine(args.database_url)
    factory=create_session_factory(engine)
    market=SqlAlchemyMarketDataRepository(factory)
    instrument=market.resolve_instrument(symbol=args.product,exchange=args.exchange)
    series=market.load_continuous_bars(instrument_id=instrument.instrument_id,as_of=as_of,limit=2000)
    dates=[bar.trading_date for bar in series]
    index={bar.trading_date:bar.research_index for bar in series}
    analyst=FuturesMarketAnalyst(context_builder=SqlAlchemyMarketContextBuilder(market),analysis_repository=SqlAlchemyAnalysisRepository(factory))
    records=[]
    errors=[]
    for day in dates[-args.days:]:
        stamp=datetime.combine(day,as_of.timetz())
        try:
            analysis=analyst.analyze(AnalysisRequest(symbol=args.product,exchange=args.exchange,as_of=stamp,include_narrative=False))
        except FuturesAgentError as exc:
            errors.append({'day':str(day),'error':str(exc)})
            continue
        labels={f'research_return_{h}d':next_session_label(index,dates,day,h) for h in (5,20,60)}
        records.append(ReplayRecord(stamp,analysis,labels))
    print(json.dumps({'status':'experimental','g2':'NOT_ACCEPTED','data_modes':sorted({record.analysis.data_mode for record in records}),'sessions':len(records),'errors':errors,'labelled_sessions_5d':sum(r.labels['research_return_5d'] is not None for r in records),'buckets':[asdict(b) for b in summarize_direction_buckets(records,'research_return_5d')],'note':'Descriptive research returns only; no fills, costs, or validated out-of-sample edge.'},ensure_ascii=False,indent=2,default=str))
    engine.dispose()


if __name__=='__main__':
    main()
