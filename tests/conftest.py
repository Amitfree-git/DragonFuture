from __future__ import annotations

import pytest

from dragonboat_ai.futures_agent.infrastructure.database import models as _models  # noqa: F401
from dragonboat_ai.futures_agent.infrastructure.database.base import Base
from dragonboat_ai.futures_agent.infrastructure.database.repositories import (
    SqlAlchemyAnalysisRepository,
    SqlAlchemyMarketDataRepository,
)
from dragonboat_ai.futures_agent.infrastructure.database.session import (
    create_session_factory,
    create_sqlite_engine,
)


@pytest.fixture
def database(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'futures_test.db'}"
    engine = create_sqlite_engine(database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    yield {
        "url": database_url,
        "engine": engine,
        "session_factory": session_factory,
        "market_repository": SqlAlchemyMarketDataRepository(session_factory),
        "analysis_repository": SqlAlchemyAnalysisRepository(session_factory),
    }
    engine.dispose()
