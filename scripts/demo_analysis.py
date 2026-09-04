from __future__ import annotations

import argparse
import json
from pathlib import Path

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest
from dragonboat_ai.futures_agent.infrastructure.database import models as _models  # noqa: F401
from dragonboat_ai.futures_agent.infrastructure.database.base import Base
from dragonboat_ai.futures_agent.infrastructure.demo_data import seed_reference_market
from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyAnalysisRepository,
    SqlAlchemyMarketDataRepository,
)
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)


def reset_sqlite_database(database_url: str) -> None:
    """Remove the disposable demo database and its WAL sidecars."""

    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        return
    database_path = Path(database_url.removeprefix("sqlite:///"))
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{database_path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic synthetic RB analysis")
    parser.add_argument("--database-url", default="sqlite:///data/futures_demo.db")
    parser.add_argument("--output", default="outputs/demo_analysis.json")
    parser.add_argument(
        "--keep-database",
        action="store_true",
        help="Do not reset the disposable SQLite demo database before seeding it.",
    )
    args = parser.parse_args()

    if not args.keep_database:
        reset_sqlite_database(args.database_url)

    engine = create_sqlite_engine(args.database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    market_repository = SqlAlchemyMarketDataRepository(session_factory)
    analysis_repository = SqlAlchemyAnalysisRepository(session_factory)

    fixture = seed_reference_market(market_repository)

    analyst = FuturesMarketAnalyst(
        context_builder=SqlAlchemyMarketContextBuilder(market_repository),
        analysis_repository=analysis_repository,
    )
    result = analyst.analyze(
        AnalysisRequest(
            symbol="RB",
            exchange="SHFE",
            as_of=fixture["as_of"],
            horizon="swing",
            include_narrative=True,
        )
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "analysis_id": result.analysis_id,
                "contract": result.selected_contract,
                "regime": result.regime.primary,
                "direction_score": result.direction.score,
                "direction": result.direction.label.value,
                "opportunity_score": result.opportunity.score,
                "action": result.opportunity.action.value,
                "confidence": result.confidence.score,
                "risk": result.risk.score,
                "output": str(output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    engine.dispose()


if __name__ == "__main__":
    main()
