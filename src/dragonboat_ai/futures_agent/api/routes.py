from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastapi import APIRouter, HTTPException, Query, Request

from dragonboat_ai.futures_agent.domain.exceptions import FuturesAgentError
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FuturesMarketAnalysis

router = APIRouter(prefix="/api/v1/futures", tags=["futures-market-analyst"])
BATCH_LIMIT = 20


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "futures-market-analyst"}


@router.get("/ready")
def ready(request: Request) -> dict:
    from sqlalchemy import inspect, text
    from dragonboat_ai.futures_agent.infrastructure.database.base import Base
    try:
        inspector = inspect(request.app.state.engine)
        for table in Base.metadata.sorted_tables:
            actual = {col["name"] for col in inspector.get_columns(table.name)}
            if not set(table.columns.keys()) <= actual:
                raise ValueError("schema_migration_required")
        with request.app.state.engine.connect() as connection:
            bars = connection.scalar(text("SELECT count(*) FROM fut_bar_daily"))
            analyses = connection.scalar(text("SELECT count(*) FROM fut_analysis_run"))
        if not bars or not analyses:
            raise ValueError("market_data_or_analysis_missing")
    except Exception:
        raise HTTPException(status_code=503, detail="database_schema_or_analysis_not_ready")
    return {"status": "ready", "service": "futures-market-analyst",
            "scope": "experimental_research", "production_ready": False}


@router.post("/analyses", response_model=FuturesMarketAnalysis)
def create_analysis(payload: AnalysisRequest, request: Request) -> FuturesMarketAnalysis:
    try:
        return request.app.state.analyst.analyze(payload)
    except FuturesAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/analyses/batch")
def create_analysis_batch(payload: list[AnalysisRequest], request: Request) -> dict:
    if len(payload) > BATCH_LIMIT:
        raise HTTPException(status_code=413, detail=f"batch exceeds {BATCH_LIMIT} items")
    results: list[FuturesMarketAnalysis] = []
    errors: list[dict[str, str]] = []
    for item in payload:
        try:
            results.append(request.app.state.analyst.analyze(item))
        except FuturesAgentError as exc:
            errors.append({"symbol": item.symbol, "error": str(exc)})
    return {"results": results, "errors": errors}


@router.get("/analyses/{analysis_id}", response_model=FuturesMarketAnalysis)
def get_analysis(analysis_id: str, request: Request) -> FuturesMarketAnalysis:
    result = request.app.state.analysis_repository.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/symbols/{symbol}/latest", response_model=FuturesMarketAnalysis)
def latest_analysis(
    symbol: str,
    request: Request,
    horizon: str,
    exchange: str | None = Query(default=None),
    contract: str | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
) -> FuturesMarketAnalysis:
    result = request.app.state.analysis_repository.latest(
        symbol.upper(),
        horizon,
        exchange=exchange,
        contract=contract,
        as_of=as_of,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/analyses/{analysis_id}/invalidation")
def invalidation_status(analysis_id: str, request: Request) -> dict:
    from dragonboat_ai.futures_agent.invalidation.service import read_invalidation
    repository = request.app.state.analysis_repository
    original = repository.get(analysis_id)
    if original is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return read_invalidation(repository.session_factory, original)


@router.get('/catalog')
def data_catalog(request: Request) -> dict:
    from sqlalchemy import text
    try:
        with request.app.state.engine.connect() as connection:
            rows=connection.execute(text('''
                SELECT i.symbol, i.exchange, count(b.bar_id) AS bars,
                       min(b.trading_date) AS first_session, max(b.trading_date) AS last_session,
                       group_concat(DISTINCT b.data_mode) AS data_modes
                FROM fut_instrument i
                JOIN fut_contract c ON c.instrument_id=i.instrument_id
                JOIN fut_bar_daily b ON b.contract_id=c.contract_id
                LEFT JOIN fut_data_batch d ON d.batch_id=b.data_batch_id
                WHERE b.data_batch_id IS NULL OR d.status='committed'
                GROUP BY i.symbol, i.exchange
            ''')).mappings().all()
        return {'service':'DragonFuture','production_ready':False,
                'scope':'experimental_research','code_artifact':request.app.state.analyst.versions.code_commit,
                'instruments':[dict(row) for row in rows],
                'usage':'Historical final_only data is not strict PIT or a live trading feed.'}
    except Exception:
        raise HTTPException(status_code=503,detail='market_catalog_not_ready')


class RefreshAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=12, pattern=r"^[A-Z]+$")
    exchange: Literal["SHFE", "DCE", "CZCE", "CFFEX", "INE", "GFEX"]
    horizon: Literal["swing", "position"] = "swing"

    @field_validator("symbol", "exchange", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


@router.post("/refresh_and_analyze")
def refresh_and_analyze(payload: RefreshAnalysisRequest, request: Request) -> dict:
    from dragonboat_ai.futures_agent.application.refresh import RefreshError
    try:
        return request.app.state.refresh_service.run(**payload.model_dump())
    except RefreshError as exc:
        raise HTTPException(status_code=exc.status_code, detail={
            "status": "refresh_failed", "code": exc.code, "consumer_intent": "blocked",
        }) from exc
