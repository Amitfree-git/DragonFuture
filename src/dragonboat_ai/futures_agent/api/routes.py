from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from dragonboat_ai.futures_agent.domain.exceptions import FuturesAgentError
from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FuturesMarketAnalysis

router = APIRouter(prefix="/api/v1/futures", tags=["futures-market-analyst"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "futures-market-analyst"}


@router.post("/analyses", response_model=FuturesMarketAnalysis)
def create_analysis(payload: AnalysisRequest, request: Request) -> FuturesMarketAnalysis:
    try:
        return request.app.state.analyst.analyze(payload)
    except FuturesAgentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/analyses/{analysis_id}", response_model=FuturesMarketAnalysis)
def get_analysis(analysis_id: str, request: Request) -> FuturesMarketAnalysis:
    result = request.app.state.analysis_repository.get(analysis_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result


@router.get("/symbols/{symbol}/latest", response_model=FuturesMarketAnalysis)
def latest_analysis(symbol: str, horizon: str, request: Request) -> FuturesMarketAnalysis:
    result = request.app.state.analysis_repository.latest(symbol.upper(), horizon)
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result
