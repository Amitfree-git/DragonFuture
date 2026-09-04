from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol

from dragonboat_ai.futures_agent.domain.exceptions import NarrativeValidationError
from dragonboat_ai.futures_agent.domain.models import (
    FuturesMarketAnalysis,
    NarrativeOutput,
)

from .prompt import SYSTEM_PROMPT_ZH, build_narrative_payload

_EVIDENCE_REFERENCE = re.compile(r"\[evidence_id=([A-Za-z0-9_-]+)\]")


class StructuredCompletionClient(Protocol):
    """Provider-neutral boundary for JSON-schema-capable model clients."""

    def complete_json(
        self,
        *,
        system_prompt: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        ...


class LLMNarrativeGenerator:
    """Generate and validate narrative without exposing score mutation hooks."""

    def __init__(self, client: StructuredCompletionClient) -> None:
        self.client = client

    def generate(self, core_result: FuturesMarketAnalysis) -> NarrativeOutput:
        raw = self.client.complete_json(
            system_prompt=SYSTEM_PROMPT_ZH,
            payload=build_narrative_payload(core_result),
        )
        output = NarrativeOutput.model_validate(raw)
        self._validate_evidence_references(core_result, output)
        return output

    @staticmethod
    def _validate_evidence_references(
        core_result: FuturesMarketAnalysis,
        output: NarrativeOutput,
    ) -> None:
        known_ids = {item.evidence_id for item in core_result.evidence}
        for section_name, claims in (
            ("bullish_case", output.bullish_case),
            ("bearish_case", output.bearish_case),
        ):
            for claim in claims:
                references = set(_EVIDENCE_REFERENCE.findall(claim))
                if not references:
                    raise NarrativeValidationError(
                        f"{section_name} claim is missing an evidence_id reference"
                    )
                unknown = references - known_ids
                if unknown:
                    raise NarrativeValidationError(
                        f"{section_name} claim references unknown evidence IDs: {sorted(unknown)}"
                    )
