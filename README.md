# DragonFuture — Futures Market Analyst Agent V1

DragonFuture is a deterministic, point-in-time-safe daily futures market analysis service. Its Python package remains under `dragonboat_ai.futures_agent` so it can also be merged into DragonBoatAI without changing import paths.

中文说明见 [`README.zh-CN.md`](README.zh-CN.md)。

## What is implemented

- Strict Pydantic v2 domain models for market state, direction, opportunity, confidence, risk, evidence and invalidation.
- Typed SQLAlchemy 2.0 models for 20 normalized SQLite tables.
- Alembic initial migration with verified upgrade, downgrade and re-upgrade paths.
- Point-in-time market-data reads using `available_at` and latest-visible revisions.
- Real-contract storage for settlement, volume, open interest and term structure.
- Back-adjusted continuous-series lineage for trend, momentum and volatility features.
- Deterministic feature, factor, regime, direction, confidence, risk, opportunity and invalidation engines.
- Main-contract selection with expiry filtering and multi-day challenger confirmation.
- Deterministic fallback narrative that cannot change scores.
- Provider-neutral structured LLM narrative adapter with mandatory evidence-ID validation.
- FastAPI endpoints and a synthetic end-to-end demo.
- Unit, integration and look-ahead-leakage tests.

## V1 boundary

V1 is daily and medium/low frequency. It does not consume Tick, Level-2, second-level or minute-level data. It does not place orders, size positions, promise returns or let an LLM calculate indicators. News, weather, inventory, basis, commodity-specific fundamentals and ML forecasts are intentionally deferred.

## Core invariants

1. A query at `as_of` can read only records where `available_at <= as_of`.
2. Data revisions are appended; prior revisions are not overwritten.
3. Continuous prices are used for trend/momentum/volatility, while real contracts remain the source for positioning, liquidity, expiry and the curve.
4. Missing factors remain missing. They are never converted to neutral zero scores.
5. Direction and opportunity are separate outputs.
6. Hard risk gates override a high direction score.
7. The deterministic core remains usable if narrative generation fails.
8. Every run records input, configuration and result hashes plus model versions.

## Project layout

```text
src/dragonboat_ai/futures_agent/
├── api/                 FastAPI composition and routes
├── application/         Context construction and analysis orchestration
├── contracts/           Main-contract and continuous-series rules
├── domain/              Enums, Pydantic models and market-data dataclasses
├── features/            Daily feature calculations and normalization
├── infrastructure/      SQLite/SQLAlchemy repositories and schema
├── invalidation/        Thesis invalidation rules
├── narrative/           Deterministic fallback renderer
├── ports/               Repository and service protocols
├── regime/              Rule-based market-state classifier
└── scoring/             Factor, direction, confidence, risk and opportunity engines
```

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Initialize through Alembic:

```bash
alembic upgrade head
```

Or initialize a disposable local database directly:

```bash
python scripts/init_db.py --database-url sqlite:///data/futures_agent.db
```

Run all tests:

```bash
pytest -q
```

Run the synthetic RB demonstration:

```bash
python scripts/demo_analysis.py
```

The command resets its disposable demo database by default and writes the complete JSON to
`outputs/demo_analysis.json`. Pass `--keep-database` only when the supplied database has not
already been seeded.

Start the API:

```bash
uvicorn dragonboat_ai.futures_agent.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/futures/health
```

Create an analysis after real market data has been loaded:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/futures/analyses \
  -H 'Content-Type: application/json' \
  -d '{
    "symbol": "RB",
    "exchange": "SHFE",
    "horizon": "swing",
    "as_of": "2026-09-04T16:30:00+08:00",
    "include_narrative": true
  }'
```

## Integration into the existing DragonBoatAI repository

This package is intentionally shaped as a drop-in addition rather than a replacement repository.

1. Copy `src/dragonboat_ai/futures_agent/` into the existing `src/dragonboat_ai/` tree.
2. Merge, rather than overwrite, the dependency entries from this `pyproject.toml`.
3. Copy the Alembic revision into the existing migration tree and set its `down_revision` to the current repository head.
4. Reuse the existing engine/session factory by adapting `SqlAlchemyMarketDataRepository` and `SqlAlchemyAnalysisRepository` construction.
5. Replace `infrastructure/demo_data.py` with the actual data-source ingestion path; it is synthetic and exists only for verification.
6. Preserve the `available_at`, `revision_no`, `payload_hash`, `input_data_hash` and version fields.
7. Run the full existing test suite as well as the included futures tests before merging.

## Production data adapter contract

At minimum, a daily data adapter must populate:

- instrument and real-contract metadata;
- real-contract OHLC, settlement, volume and open interest;
- `available_at` for each publication or revision;
- back-adjusted continuous settlement with source-contract lineage;
- same-time curve snapshots containing at least two liquid real contracts.

Settlement and close remain separate fields.

## API output model

The machine-readable result contains:

```text
Market Regime
Direction
Opportunity
Confidence
Risk
Invalidation
Metrics
Evidence
Versions and hashes
Optional narrative
```

Downstream Strategy, Portfolio, CIO, Risk and Execution agents should consume the structured fields. They should not parse the natural-language narrative to recover scores.

## Validation status

The scaffold was executed with Python 3.13.5, Pydantic 2.13.4, SQLAlchemy 2.0.50, FastAPI 0.128.2, Alembic 1.18.4 and pytest 9.0.2 in the build environment. The package keeps compatible major-version ranges rather than pinning to one patch release.
