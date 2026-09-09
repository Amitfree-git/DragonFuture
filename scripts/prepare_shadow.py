"""Ingest real Tushare/MCP captures, build mapping, prepare a shadow database."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from dragonboat_ai.futures_agent.contracts.mapping_pipeline import (
    build_mapping_and_continuous,
    calendar_from_trade_cal,
    ingest_trade_calendar,
)
from dragonboat_ai.futures_agent.infrastructure.database.calendar_store import SqlAlchemyCalendarStore
from dragonboat_ai.futures_agent.infrastructure.database.repositories import SqlAlchemyMarketDataRepository
from dragonboat_ai.futures_agent.infrastructure.database.schema import create_schema
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)
from dragonboat_ai.futures_agent.infrastructure.ingestion.captured import CapturedFuturesSource
from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareFuturesClient
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_mapper import SHANGHAI, parse_trade_date


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a real-data shadow database (not G3).")
    parser.add_argument("--product", default="RB")
    parser.add_argument("--exchange", default="SHFE")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--database-url", default="sqlite:///data/futures_shadow.db")
    parser.add_argument("--source", choices=("tushare", "capture"), default="tushare")
    parser.add_argument("--capture-dir", default="data/captures/tushare/RB_SHFE")
    parser.add_argument("--token", default=os.environ.get("TUSHARE_TOKEN", ""))
    args = parser.parse_args()

    create_schema(args.database_url)
    engine = create_sqlite_engine(args.database_url)
    factory = create_session_factory(engine)
    market = SqlAlchemyMarketDataRepository(factory)
    if args.source == "capture":
        source = CapturedFuturesSource(args.capture_dir)
        calendar_rows: list[dict] = []
        mapping_rows: list[dict] = []
        capture = Path(args.capture_dir)
        cal_path = capture / "trade_cal.json"
        map_path = capture / "fut_mapping.json"
        if cal_path.exists():
            calendar_rows = json.loads(cal_path.read_text(encoding="utf-8"))
        if map_path.exists():
            mapping_rows = json.loads(map_path.read_text(encoding="utf-8"))
    else:
        client = TushareFuturesClient(args.token)
        source = client
        calendar_rows = client.fetch_trade_cal(exchange=args.exchange, start=args.start, end=args.end)
        mapping_rows = client.fetch_mapping(
            product=args.product, exchange=args.exchange, start=args.start, end=args.end
        )

    report = TushareMarketIngestor(market, source).ingest(
        product=args.product,
        exchange=args.exchange,
        start=args.start,
        end=args.end,
    )
    if calendar_rows:
        ingest_trade_calendar(SqlAlchemyCalendarStore(factory), calendar_rows)
    end_date = parse_trade_date(args.end)
    as_of = datetime(end_date.year, end_date.month, end_date.day, 16, 0, tzinfo=SHANGHAI)
    mapping = build_mapping_and_continuous(
        market,
        symbol=args.product,
        exchange=args.exchange,
        as_of=as_of,
        calendar=calendar_from_trade_cal(calendar_rows, exchange=args.exchange) if calendar_rows else None,
    )
    out = Path("data/captures") / f"{args.product}_{args.exchange}_prep.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    mapping_path = Path("data/captures") / f"{args.product}_{args.exchange}_fut_mapping.json"
    if mapping_rows:
        mapping_path.write_text(json.dumps(mapping_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {
        "status": "EXPERIMENTAL_DRESS_REHEARSAL",
        "g3": "NOT_RUN",
        "data_mode": "final_only",
        "ingest": {
            "manifest_id": report.manifest_id,
            "contracts": report.contracts,
            "bars_inserted": report.bars_inserted,
            "bars_dropped_missing": report.bars_dropped_missing,
            "curves": report.curves,
            "missing_trading_dates": list(report.coverage.missing_trading_dates) if report.coverage else [],
        },
        "mapping": {
            "sessions": mapping.sessions,
            "mappings": mapping.mappings,
            "rolls": mapping.rolls,
            "continuous_bars": mapping.continuous_bars,
            "blocked_sessions": mapping.blocked_sessions,
        },
        "tushare_mapping_file": str(mapping_path) if mapping_rows else None,
        "tushare_mapping_rows": len(mapping_rows),
        "note": "Tushare fut_mapping is a review reference, not the PIT main-contract truth.",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    engine.dispose()


if __name__ == "__main__":
    main()
