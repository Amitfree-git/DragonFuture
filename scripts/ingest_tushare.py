from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyMarketDataRepository,
)
from dragonboat_ai.futures_agent.infrastructure.database.schema import create_schema
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)
from dragonboat_ai.futures_agent.infrastructure.ingestion.pipeline import TushareMarketIngestor
from dragonboat_ai.futures_agent.infrastructure.ingestion.tushare_client import TushareFuturesClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Tushare futures contracts, daily bars and same-session curve snapshots."
    )
    parser.add_argument("--product", default="RB")
    parser.add_argument("--exchange", default="SHFE")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--database-url", default="sqlite:///data/futures_agent.db")
    parser.add_argument("--token", default=os.environ.get("TUSHARE_TOKEN", ""))
    args = parser.parse_args()

    create_schema(args.database_url)
    engine = create_sqlite_engine(args.database_url)
    session_factory = create_session_factory(engine)
    report = TushareMarketIngestor(
        SqlAlchemyMarketDataRepository(session_factory),
        TushareFuturesClient(args.token),
    ).ingest(product=args.product, exchange=args.exchange, start=args.start, end=args.end)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, default=str))
    engine.dispose()


if __name__ == "__main__":
    main()
