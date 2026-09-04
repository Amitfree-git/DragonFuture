from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dragonboat_ai.futures_agent.domain.models import AnalysisRequest, FactorAssessment
from dragonboat_ai.futures_agent.domain.enums import DataStatus, FactorName


def test_analysis_request_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        AnalysisRequest(symbol="rb", as_of=datetime(2026, 9, 4, 16, 0))


def test_analysis_request_normalizes_codes() -> None:
    request = AnalysisRequest(
        symbol=" rb ",
        exchange="shfe",
        contract="rb2701",
        as_of=datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
    )
    assert request.symbol == "RB"
    assert request.exchange == "SHFE"
    assert request.contract == "RB2701"


def test_score_bounds_are_enforced() -> None:
    with pytest.raises(ValidationError):
        FactorAssessment(
            factor=FactorName.TREND,
            status=DataStatus.OK,
            score=101,
            coverage=100,
            confidence=100,
        )
