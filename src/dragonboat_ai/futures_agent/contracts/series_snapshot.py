from __future__ import annotations

from dataclasses import dataclass

from dragonboat_ai.futures_agent.contracts.continuous_series import (
    AdjustedContinuousPoint,
    BackwardAdditiveContinuousSeriesBuilder,
    RawContinuousPoint,
    RollGap,
)
from dragonboat_ai.futures_agent.infrastructure.ingestion.hashing import stable_payload_hash


@dataclass(frozen=True, slots=True)
class ChartSeriesSnapshot:
    snapshot_id: str
    input_hash: str
    points: tuple[AdjustedContinuousPoint, ...]


class ChartSeriesStore:
    """In-process immutable vintage of a backward-additive chart series."""

    def __init__(self) -> None:
        self._snapshots: dict[str, ChartSeriesSnapshot] = {}

    def build_and_save(
        self,
        snapshot_id: str,
        points: list[RawContinuousPoint],
        roll_gaps: list[RollGap],
    ) -> ChartSeriesSnapshot:
        built = tuple(BackwardAdditiveContinuousSeriesBuilder().build(points, roll_gaps))
        payload_hash = stable_payload_hash(
            {
                "points": [
                    (item.trading_date.isoformat(), item.source_contract, str(item.settlement))
                    for item in points
                ],
                "gaps": [
                    (item.effective_date.isoformat(), item.from_contract, item.to_contract, str(item.additive_gap))
                    for item in roll_gaps
                ],
            }
        )
        existing = self._snapshots.get(snapshot_id)
        if existing is not None:
            if existing.input_hash != payload_hash:
                raise ValueError(f"chart series snapshot {snapshot_id} is immutable")
            return existing
        snapshot = ChartSeriesSnapshot(snapshot_id=snapshot_id, input_hash=payload_hash, points=built)
        self._snapshots[snapshot_id] = snapshot
        return snapshot

    def get(self, snapshot_id: str) -> ChartSeriesSnapshot | None:
        return self._snapshots.get(snapshot_id)
