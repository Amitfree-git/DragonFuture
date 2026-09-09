from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from dragonboat_ai.futures_agent.operations.shadow import ShadowObservation


REVIEW_COLUMNS = (
    "selected_contract_ok",
    "curve_direction_ok",
    "limit_handling_ok",
    "assumptions_ok",
    "invalidation_ok",
    "reviewer_notes",
)


def write_review_worksheet(
    path: Path,
    observations: list[ShadowObservation],
    *,
    tushare_mapping: dict[date, str] | None = None,
    extra: list[dict[str, Any]] | None = None,
) -> Path:
    extra_by_date = {item["session_date"]: item for item in (extra or [])}
    mapping = tushare_mapping or {}
    lines = [
        "# Shadow human-review worksheet",
        "",
        "Fill the `_ok` columns with `yes` / `no` / `n/a`. This is not G3 until",
        "20 **live-captured** sessions are reviewed. Historical `final_only` replay is a dress rehearsal.",
        "",
        "| session_date | our_contract | tushare_mapping | action | hard_gate | gap | candidate | core_hash | "
        + " | ".join(REVIEW_COLUMNS)
        + " |",
        "|---|---|---|---|---|---|---|---" + "|---" * len(REVIEW_COLUMNS) + "|",
    ]
    for item in observations:
        details = extra_by_date.get(item.session_date, {})
        contract = details.get("selected_contract") or ""
        tushare = mapping.get(item.session_date, "")
        core = (item.core_result_hash or "")[:12]
        blanks = " | ".join("" for _ in REVIEW_COLUMNS)
        lines.append(
            f"| {item.session_date.isoformat()} | {contract} | {tushare} | "
            f"{item.opportunity_action or ''} | {item.hard_gate} | {item.gap} | "
            f"{item.candidate_emitted} | `{core}` | {blanks} |"
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
