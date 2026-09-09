# MCP Source Implementation Plan

Goal: Make the authorized local MCP server a configurable DragonFuture market source.
Architecture: A bounded stdio JSON-RPC session per refresh, a strict source adapter, and an explicit source factory. Keep Tushare data semantics, main selection, risk and historical version logic. No automatic source fallback.

Approved scope: prior MCP acceptance reports and user's instruction to start integration.

- [x] Add failing source/transport/config tests, including null limits, wrong identity, truncation and timeout.
- [x] Implement stdio session with initialization, bounded reads, sanitized errors and process cleanup.
- [x] Implement source adapter for contract master, explicit daily contracts, ft_limit and calendar, preserving canonical raw fields and query provenance.
- [x] Wire configuration and refresh session lifetime; archive MCP provenance before committing the ingest batch.
- [x] Run regression and isolated refresh tests, compare live MCP/direct data across RB/M rolls.
- [x] Document configuration and explicit rollback; switch the local launcher after isolated end-to-end parity passes.

Configuration: DRAGONBOAT_FUTURES_SOURCE=tushare_http|mcp; MCP command is a JSON argv array in DRAGONBOAT_FUTURES_MCP_COMMAND; timeout is DRAGONBOAT_FUTURES_MCP_TIMEOUT. No shell command interpolation. Credentials inherited by the MCP process and never logged.

Acceptance: rejected envelopes/truncation/identity errors never produce committed partial refresh batches; session closes on every outcome; raw supplier numbers and missing values match the direct route; final_only is preserved.
