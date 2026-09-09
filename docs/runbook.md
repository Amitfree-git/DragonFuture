# Runbook (experimental / trial)

This is an operations draft for the read-only analyst. It is **not** a production
acceptance record. Shadow observation days: **0**. G3 and G4 are **not** met.

## What this service does

- Computes a structured futures market analysis.
- Emits `futures.market_analysis.published` into `fut_event_outbox` in the **same
  database transaction** as the analysis row.
- Never sends orders. Downstream must read `action` and `hard_gate`. `no_trade`
  and `insufficient_data` are **blocked**, not weak buys or sells.

## Daily shadow loop

1. Wait until the **exchange session is closed** (SHFE/DCE/CZCE/INE/GFEX 15:00,
   CFFEX 15:15 Asia/Shanghai). Do not use a hardcoded 16:30.
2. Confirm `settlement_available_at` is already visible and not in the future of
   `now`. If missing or stale, record a **gap** and skip. Do not invent a
   settlement.
3. Run `scripts/run_shadow.py` only against a committed vintage. The normal path reads an explicitly selected ingested database; `--synthetic` is a separate demonstration option. Historical replay remains experimental.
4. Review `fut_shadow_run` for gaps, hard gates, selected contract, and whether
   a candidate was emitted.

## Authentication

- Optional bearer token: set `DRAGONBOAT_FUTURES_API_TOKEN`.
- `/api/v1/futures/health` and `/ready` stay public.
- When the token is set, analysis routes return **401** without `Authorization:
  Bearer <token>`.
- Process-local rate limit is 60 requests / minute / client. This is not a
  multi-node limiter.

## Backup and restore

Do **not** copy a live `*.db` file while WAL is open and call that a backup.

```bash
python - <<'PY'
from pathlib import Path
from dragonboat_ai.futures_agent.operations.backup import backup_sqlite, restore_sqlite, table_count, canonical_row_hash
url = "sqlite:///data/futures_agent.db"
backup = backup_sqlite(url, Path("data/backups/futures_agent.backup.db"))
restore_sqlite(backup, "sqlite:///data/futures_agent.restored.db")
print(table_count("sqlite:///data/futures_agent.restored.db", "fut_analysis_run"))
print(canonical_row_hash("sqlite:///data/futures_agent.restored.db", "fut_analysis_run", ("analysis_id", "core_result_hash")))
PY
```

After restore, compare row counts and the canonical hash of
`analysis_id, core_result_hash`. SQLite URLs other than `sqlite://` are rejected
by the engine; PostgreSQL is **not** supported.

## Outbox recovery

If the database commit succeeded but the downstream publish failed:

1. Rows stay in `fut_event_outbox` as `failed`.
2. Call `EventOutbox.retry_failed()` to move them back to `pending`.
3. Consumers must dedupe on `event_id` (at-least-once, not exactly-once).

## Alerts to wire (when a real window exists)

These names are implemented in `operations/observability.py`. They are not a
live pager.

| Alert | Meaning |
|---|---|
| `shadow_gap` | Watermark missing/stale/too_early or an injected fault blocked the session |
| `candidate_emitted_during_fault` | A candidate escaped a fault path — treat as a defect |
| `outbox_publish_failed` | At least one outbox row is `failed` |

On call: do not place orders from a candidate. Inspect the analysis, the
manifest, and the watermark decision. Roll back the read path by serving the
previous analysis id; rows are append-only.

## Release / rollback notes

- Schema changes go through Alembic. History rows are not deleted on downgrade
  of later application code; a downgrade that drops tables **does** drop those
  tables — do not run `downgrade` against a database that holds facts you need.
- Config and feature-set versions are part of `version_hash`. Changing them
  creates a new analysis identity rather than mutating the old one.


## 2026-09-05 corrected local service

Start with `sh scripts/serve_corrected.sh`; it selects the migrated, independently copied `data/futures_corrected.db` and binds only localhost:8000. The original `data/futures_shadow.db` remains unchanged for historical audit. Stop the current listener before restarting; do not run two writers on different code versions.

Grok Bot uses the built-in Shell tool targeting this Mac's machineId and reads `GROK_HANDOFF.md`. `scripts/grok_query.py` performs GET only and rejects mismatched code artifacts. A successful readiness response means the experimental schema and stored analyses are present, not that production G1–G4 were signed off.

Ingest and rebuild must finish before generating fresh analyses. New series are immutable, complete vintages. A historical final-only replay is not a live watermark observation. Invalidation is evaluated when analyses are created, based on actual metric sessions; no independent scheduled invalidation monitor is installed.

Shadow observations now append on repeated sessions. Migrating down after repeated sessions intentionally refuses to discard history. Do not downgrade the corrected production-copy database.


## Refresh and analyze published daily data

`POST /api/v1/futures/refresh_and_analyze` accepts `{"symbol":"RB","exchange":"SHFE","horizon":"swing"}`. Uses existing local TUSHARE_TOKEN with direct Tushare HTTP, not MCP. Source factory is lazy; missing credentials fail only when refreshing. The operation validates calendar/coverage, stages and commits market data, rebuilds coherent series and returns refresh metadata plus analysis. The operation serializes on the database; failures return blocked errors rather than stale success.

Grok entry: `.venv/bin/python -B scripts/grok_query.py refresh_and_analyze --symbol RB --exchange SHFE --horizon swing`. No historical as_of for refresh; ordinary POST /analyses remains available for historical evaluation without ingestion. Final-only history and unknown-limit risk gates remain; this is not live trading.
