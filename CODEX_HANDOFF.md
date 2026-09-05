# Codex handoff: DragonBoatAI Futures Market Analyst V1

> **新版文档入口（2026-09-05）：** 本文保留历史合并背景。请先读[详细设计](docs/DESIGN.md)、[实施主计划](docs/IMPLEMENTATION_PLAN.md)及[基线审计](docs/BASELINE_AUDIT.md)；当前先修正参考实现，不直接跳到生产集成。

## Objective

Merge the supplied futures-agent package into the existing DragonBoatAI repository without weakening point-in-time, revision-history or deterministic-scoring guarantees.

## Required sequence

1. Create a feature branch such as `feat/futures-market-analyst-v1`.
2. Inspect the repository's existing package, DB session, Alembic head, API composition and test conventions.
3. Copy the futures package into `src/dragonboat_ai/futures_agent/`.
4. Reconcile imports and reuse existing shared infrastructure where appropriate; do not rewrite domain scoring as LLM prompts.
5. Merge dependencies into the existing `pyproject.toml`.
6. Rebase the migration by changing `down_revision` to the repository's current Alembic head. Resolve table-name conflicts explicitly.
7. Wire the API router into the existing application factory.
8. Implement the real daily market-data adapter behind `MarketDataRepository`.
9. Run both the existing repository tests and the supplied tests.
10. Open a PR with schema, point-in-time behaviour and migration rollback documented.

## Non-negotiable invariants

- `available_at <= as_of` for every datum used by an analysis.
- A later correction is a new revision and cannot silently rewrite historical information sets.
- Main-contract challengers require confirmation from completed snapshots.
- Roll decisions cannot take effect retroactively.
- A continuous-series point retains its real `source_contract`.
- Missing data is not a zero score.
- Volatility changes risk/opportunity, not directional sign.
- Hard risk gates force `no_trade` even when direction is strong.
- LLM output cannot modify scores, labels or evidence.

## Acceptance commands

```bash
pytest -q
alembic upgrade head
alembic downgrade -1
alembic upgrade head
python scripts/demo_analysis.py
```

## Acceptance checks

- All supplied tests pass.
- Existing DragonBoatAI tests remain green.
- The migration works against a copy of the current SQLite database.
- A query before a revision's `available_at` returns the earlier revision.
- The same input data and version configuration produce the same `core_result_hash`.
- An LLM/narrative failure still returns the deterministic analysis JSON.
- API responses distinguish `direction`, `opportunity`, `confidence` and `risk`.

## Out of scope for this PR

- Tick, Level-2, second-level or minute-level data.
- Order routing and execution.
- Position sizing and portfolio allocation.
- Basis, inventory, news, weather or commodity-specific fundamentals.
- Machine-learning forecasts.
