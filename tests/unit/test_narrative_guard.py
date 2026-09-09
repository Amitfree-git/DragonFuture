import pytest

from dragonboat_ai.futures_agent.domain.exceptions import NarrativeValidationError
from dragonboat_ai.futures_agent.domain.models import NarrativeOutput
from dragonboat_ai.futures_agent.narrative.llm_adapter import LLMNarrativeGenerator


def test_narrative_rejects_confidence_as_win_probability() -> None:
    output = NarrativeOutput(
        executive_summary="当前置信度 72 等于获利概率。",
        market_structure="结构。",
        final_conclusion="结论。",
    )
    with pytest.raises(NarrativeValidationError, match="win probability"):
        LLMNarrativeGenerator._validate_forbidden_claims(output)
