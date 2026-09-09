# Audit remediation and Grok Bot access implementation plan

Goal: close reproducible audit defects and expose correct, explicitly experimental futures analysis to the user's Grok Bot.
Architecture: keep the independent Python analyst. Build immutable as-of research/price snapshots from committed facts; use selected-contract entry inputs and fail-closed risk/selection. Expose local read-only tools for Grok Bot using its verified extension mechanism.
Tech stack: Python, SQLAlchemy/SQLite, FastAPI; bot integration mechanism selected after inspecting installed app.

User approved repair and bot integration following the audit. Preserve all prior dirty files; pre-fix source snapshot is in the Codex task work/pre-fix directory. No trading execution, remote publication or credential changes are required.

- [x] 1. Add failing full-path tests for all-history versus incremental continuous series, future roll perturbation, blocked mappings and missing calendar sessions. Fix immutable snapshots and research-index input; verify stable original as-of output. Files: contracts/mapping_pipeline.py, contracts/main_contract_state.py, infrastructure/database/repositories.py, domain/market_data.py, application/context_builder.py, features/engine.py and focused integration tests. Add migration only if required, preserve legacy read records.
- [x] 2. Add failing tests for absent mandatory risk keys and independently stale dependencies. Fix scoring/risk_engine.py and data_quality.py; preserve actual unknown-limit hard gate.
- [x] 3. Add failing train/validation boundary label tests. Fix research/replay.py to purge by label end trading session, including embargo at both boundaries; wire meaningful labelled CLI evaluation.
- [x] 4. Add failing core-persisted-before-narrative and readiness tests. Fix analyst ordering, explicit source/code identity, and real schema/data readiness. Never migrate business DB implicitly.
- [x] 5. Complete and test persistent invalidation lifecycle and append-only shadow history where needed for read-only consumer correctness; correct raw capture timestamp/storage provenance.
- [x] 6. Inspect Grok Bot's local supported extension config. Build bounded read-only analysis tools with explicit mode, no_trade and risk information; test malformed/stale/blocked results. Install the verified integration and validate tool discovery without sending messages externally.
- [x] 7. Run full tests, branch coverage, clean and data-preserving migrations, integration smoke on a rebuilt database copy; perform independent spec and code review and resolve failures.
- [x] 8. Restart only the relevant local service against corrected data, verify API and bot discovery, retain original database/history and document rollback and remaining real-data research gates.

Verification examples:
- pytest tests/integration/test_audit_series.py -q (new regression initially fails, then passes).
- Mandatory risk key omitted => hard_gate_triggered is True.
- Recent contract + 30-day-stale continuous => blocking_issues contains stale dependency.
- For every train record: label_end < validation_start. For validation: label_end < test_start.
- Narrative test generator checks analysis_repository.get(core.analysis_id) already exists.
- /ready on empty/legacy schema returns 503; prepared validated schema returns a diagnostic readiness object.
- Grok tool lists RB result with final_only and no_trade unchanged; never infer order from direction.

Execution status (2026-09-05): 174 tests passed. Corrected database migrated and rebuilt; service switched to localhost:8000 and status/latest/ready verified. Steps 6 and 8 remain partially open only for Grok Bot actual invocation/acknowledgment: Mac is locked and CUA requires manual unlock. Native local Shell/Read with explicit machineId is the verified access mechanism; no cloud MCP configuration was changed. GROK_HANDOFF.md contains the prepared handoff. Production G2/G3/G4 remain unaccepted.

Handoff update: Mac unlocked and the futures bot was opened. Automatic approval review rejected transmitting the handoff instructions because explicit authorization to disclose local paths and request local Read/Shell access to Grok was required. Nothing sent; user confirmation pending. Service and native CLI remain verified.

Final handoff acceptance (2026-09-05 16:40): User explicitly authorized disclosure of invocation paths and research results and active analysis requests. Grok futures bot invoked the existing POST endpoint on this Mac, read back the saved result and recorded the entry point. Analysis 330b757e-4b24-4891-ad10-8c148cd46fc1, hash 1a68d05297066b0f1a9b222d3f41ccfbbc3992652ec4a0e3a42712e185ff098d independently verified by GET. no_trade and hard_gate preserved. Prior approval/UI blockers resolved. Existing read-only query CLI remains unchanged; GROK_HANDOFF.md documents active POST computation, which persists research records and does not ingest new data or trade.
