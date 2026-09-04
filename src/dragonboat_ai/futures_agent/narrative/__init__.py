"""Narrative adapters and evidence-grounded prompt contracts."""

from .fallback import TemplateNarrativeGenerator
from .llm_adapter import LLMNarrativeGenerator, StructuredCompletionClient
from .prompt import SYSTEM_PROMPT_ZH, build_narrative_payload

__all__ = [
    "LLMNarrativeGenerator",
    "SYSTEM_PROMPT_ZH",
    "StructuredCompletionClient",
    "TemplateNarrativeGenerator",
    "build_narrative_payload",
]
