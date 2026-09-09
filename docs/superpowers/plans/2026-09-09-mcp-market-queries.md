# MCP market query synchronization

User-approved scope: sync newly available HK/US data capabilities; screenshot also identifies missing supplier mapping and roll wrappers.

Design: separate read-only McpMarketQueries and market-data HTTP router. Reuse existing bounded stdio session; whitelist three tools. Preserve complete/incomplete semantics and Yahoo adjustment/timezone/currency. No stock ingestion or futures scoring, no change to default source selection.

- [x] Inspect current MCP schemas and Yahoo return semantics.
- [x] Add failing adapter/API tests, implement wrappers, validate identity/date bounds and sanitized failures.
- [x] Verify live Tencent HK / AAPL and RB mapping/roll queries.
- [x] Run full tests and update Grok documentation.
- [x] Independent review and running service HTTP acceptance.
