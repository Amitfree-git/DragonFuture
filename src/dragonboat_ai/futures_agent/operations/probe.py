from __future__ import annotations

import platform
import time
from dataclasses import dataclass

from dragonboat_ai.futures_agent.domain.models import AnalysisRequest


@dataclass(frozen=True, slots=True)
class ProbeReport:
    samples: int
    mean_ms: float
    max_ms: float
    machine: str
    notes: str


def measure_analysis_latency(analyst, request: AnalysisRequest, *, samples: int = 3) -> ProbeReport:
    timings: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        analyst.analyze(request.model_copy(update={"force_refresh": True, "include_narrative": False}))
        timings.append((time.perf_counter() - started) * 1000.0)
    machine = f"{platform.system()} {platform.machine()} {platform.python_version()}"
    return ProbeReport(
        samples=samples,
        mean_ms=sum(timings) / len(timings),
        max_ms=max(timings),
        machine=machine,
        notes="Measured locally. Not a production SLO. Do not copy these numbers into a capacity claim.",
    )
