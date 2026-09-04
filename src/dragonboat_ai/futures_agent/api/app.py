from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from dragonboat_ai.futures_agent.application.analyst import FuturesMarketAnalyst
from dragonboat_ai.futures_agent.application.context_builder import SqlAlchemyMarketContextBuilder
from dragonboat_ai.futures_agent.infrastructure.database.base import Base
from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyAnalysisRepository,
    SqlAlchemyMarketDataRepository,
)
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)
from dragonboat_ai.futures_agent.scoring.config import ScoringConfig

from .routes import router


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_url = database_url or os.getenv(
        "DRAGONBOAT_FUTURES_DATABASE_URL",
        "sqlite:///data/futures_agent.db",
    )
    engine = create_sqlite_engine(resolved_url)
    # Explicit Alembic migrations remain the production path; create_all keeps
    # local demos and isolated tests self-contained.
    from dragonboat_ai.futures_agent.infrastructure.database import models as _models  # noqa: F401

    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    market_repository = SqlAlchemyMarketDataRepository(session_factory)
    analysis_repository = SqlAlchemyAnalysisRepository(session_factory)
    config_path = os.getenv("DRAGONBOAT_FUTURES_CONFIG")
    scoring_config = (
        ScoringConfig.from_yaml(Path(config_path))
        if config_path
        else ScoringConfig.default()
    )
    context_builder = SqlAlchemyMarketContextBuilder(
        market_repository,
        config=scoring_config,
    )
    analyst = FuturesMarketAnalyst(
        context_builder=context_builder,
        analysis_repository=analysis_repository,
        config=scoring_config,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        engine.dispose()

    app = FastAPI(
        title="DragonBoatAI Futures Market Analyst",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.market_repository = market_repository
    app.state.analysis_repository = analysis_repository
    app.state.analyst = analyst
    app.include_router(router)
    return app


def run() -> None:
    uvicorn.run(
        "dragonboat_ai.futures_agent.api.app:create_app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        factory=True,
    )


if __name__ == "__main__":
    run()
