from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from math import sqrt
from statistics import mean, pstdev

from dragonboat_ai.futures_agent.research.replay import ReplayRecord


@dataclass(frozen=True, slots=True)
class BucketSummary:
    name: str
    sample_size: int
    missing_rate: float
    mean_label: float | None
    mean_score: float | None


def summarize_direction_buckets(records: list[ReplayRecord], label_name: str) -> list[BucketSummary]:
    groups: dict[str, list[ReplayRecord]] = defaultdict(list)
    for record in records:
        groups[record.analysis.direction.label.value].append(record)
    summaries: list[BucketSummary] = []
    for name, items in sorted(groups.items()):
        labels = [item.labels.get(label_name) for item in items]
        present = [value for value in labels if value is not None]
        scores = [item.analysis.direction.score for item in items if item.analysis.direction.score is not None]
        summaries.append(
            BucketSummary(
                name=name,
                sample_size=len(items),
                missing_rate=1.0 - (len(present) / len(items) if items else 0.0),
                mean_label=mean(present) if present else None,
                mean_score=mean(scores) if scores else None,
            )
        )
    return summaries


def ablation_delta(
    baseline: list[ReplayRecord],
    ablated: list[ReplayRecord],
    label_name: str,
) -> float | None:
    if len(baseline) != len(ablated) or not baseline:
        return None
    pairs = []
    for left, right in zip(baseline, ablated, strict=True):
        target = left.labels.get(label_name)
        if target is None or left.analysis.direction.score is None or right.analysis.direction.score is None:
            continue
        pairs.append(abs(left.analysis.direction.score) - abs(right.analysis.direction.score))
    if not pairs:
        return None
    return mean(pairs)


def mean_with_interval(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    mu = mean(values)
    se = pstdev(values) / sqrt(len(values))
    return mu, 1.96 * se
