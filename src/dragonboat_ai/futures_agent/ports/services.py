from __future__ import annotations

from typing import Protocol

from dragonboat_ai.futures_agent.domain.models import FuturesMarketAnalysis, NarrativeOutput


class NarrativeGenerator(Protocol):
    def generate(self, core_result: FuturesMarketAnalysis) -> NarrativeOutput:
        ...
