"""Run the shadow loop on an ingested database.

Default path is real ingested data. --synthetic keeps the old demo fixture.
Historical final_only replay is a dress rehearsal, not G3 live capture.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.infrastructure.database.base import Base
from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyAnalysisRepository,
    SqlAlchemyMarketDataRepository,
)
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)
from dragonboat_ai.futures_agent.infrastructure.demo_data import seed_reference_market
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import (
    parse_trade_date,
    settlement_available_at,
)
from dragonboat_ai.futures_agent.operations.observability import summarize_journal
from dragonboat_ai.futures_agent.operations.review import write_review_worksheet
from dragonboat_ai.futures_agent.operations.shadow import ShadowRunner, SqlShadowStore
from dragonboat_ai.futures_agent.operations.watermark import evaluate_watermark


def _trading_dates(market: SqlAlchemyMarketDataRepository, symbol: str, exchange: str, start: date, end: date, as_of):
    instrument = market.resolve_instrument(symbol=symbol, exchange=exchange)
    curves = market.load_curve_snapshots(instrument_id=instrument.instrument_id, as_of=as_of, limit=2000)
    return [curve.trading_date for curve in curves if start <= curve.trading_date <= end]


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow loop on ingested data (not G3).")
    parser.add_argument("--database-url", default="sqlite:///data/futures_shadow.db")
    parser.add_argument("--product", default="RB")
    parser.add_argument("--exchange", default="SHFE")
    parser.add_argument("--start", help="YYYYMMDD inclusive")
    parser.add_argument("--end", help="YYYYMMDD inclusive")
    parser.add_argument("--days", type=int, default=20, help="Use the last N sessions if start is omitted")
    parser.add_argument("--review-out", default="outputs/shadow_review_RB.md")
    parser.add_argument("--tushare-mapping", default="")
    parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()

    engine = create_sqlite_engine(args.database_url)
    from dragonboat_ai.futures_agent.infrastructure.database import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    market = SqlAlchemyMarketDataRepository(factory)
    analysis_repo = SqlAlchemyAnalysisRepository(factory)

    if args.synthetic:
        fixture = seed_reference_market(market)
        dates = [fixture["as_of"].date()]
    else:
        if not args.end:
            raise SystemExit("--end is required unless --synthetic")
        end_date = parse_trade_date(args.end)
        as_of = settlement_available_at(end_date)
        start_date = parse_trade_date(args.start) if args.start else date.min
        dates = _trading_dates(market, args.product, args.exchange, start_date, end_date, as_of)
        if args.start is None:
            dates = dates[-args.days :]

    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market),
        analysis_repository=analysis_repo,
    )
    runner = ShadowRunner(store=SqlShadowStore(factory))
    extras = []
    tushare_map: dict[date, str] = {}
    if args.tushare_mapping:
        rows = json.loads(Path(args.tushare_mapping).read_text(encoding="utf-8"))
        for row in rows:
            tushare_map[parse_trade_date(str(row["trade_date"]))] = str(row["mapping_ts_code"]).split(".")[0]

    for session_date in dates:
        as_of_session = settlement_available_at(session_date)
        watermark = evaluate_watermark(
            exchange=args.exchange,
            session_date=session_date,
            now=as_of_session,
            settlement_available_at=as_of_session,
        )
        runner.run_session(
            exchange=args.exchange,
            symbol=args.product,
            session_date=session_date,
            now=as_of_session,
            settlement_available_at=as_of_session if watermark.run else None,
            analyze=lambda day=session_date: analyst.analyze(
                AnalysisRequest(
                    symbol=args.product,
                    exchange=args.exchange,
                    as_of=settlement_available_at(day),
                    include_narrative=False,
                )
            ),
        )
        latest = analysis_repo.latest(args.product, "swing", exchange=args.exchange, as_of=as_of_session)
        extras.append(
            {
                "session_date": session_date,
                "selected_contract": latest.selected_contract if latest else "",
            }
        )

    metrics = summarize_journal(runner.journal)
    worksheet = write_review_worksheet(
        Path(args.review_out),
        runner.journal.observations,
        tushare_mapping=tushare_map,
        extra=extras,
    )
    print(
        json.dumps(
            {
                "status": "EXPERIMENTAL",
                "g3": "NOT_RUN",
                "mode": "synthetic" if args.synthetic else "final_only_historical_replay",
                "sessions": metrics.sessions,
                "gaps": metrics.gaps,
                "candidates": metrics.candidates,
                "review_worksheet": str(worksheet),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
