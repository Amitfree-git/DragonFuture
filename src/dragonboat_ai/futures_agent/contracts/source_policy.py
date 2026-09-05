from __future__ import annotations

from dataclasses import dataclass

from dragonboat_ai.futures_agent.domain.data_mode import DataMode


@dataclass(frozen=True, slots=True)
class SourcePolicy:
    name: str
    allowed_sources: tuple[str, ...]
    data_mode: DataMode

    def allows(self, source: str) -> bool:
        return source in self.allowed_sources
