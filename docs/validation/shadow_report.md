# Shadow run report

Status: **EXPERIMENTAL / trial**. This is **not** G3.

## What ran

A `final_only` historical dress rehearsal on SHFE RB, using Tushare via the
configured token (same interfaces as the Wind/Tushare MCP). Live day-by-day
capture of 20 future sessions has **not** started.

| Item | Result |
|---|---|
| Window ingested | 2026-04-01 → 2026-09-04 |
| Contracts / bars / curve sessions | 17 / 1296 / 108 |
| Mapping sessions / rolls | 108 / 2 (`2026-04-03→04-07`, `2026-08-31→09-01`) |
| Shadow sessions | **20** (2026-08-10 → 2026-09-04) |
| Gaps | 0 |
| Candidates emitted | 0 (all `no_trade`, `hard_gate=True`) |
| Human review | Worksheet at `outputs/shadow_review_RB.md` — columns still blank |
| Watermark | Per-exchange session close; settlement stamped 16:00 Asia/Shanghai |
| Tushare `fut_mapping` | Review reference only. On 2026-09-01 this policy is already on RB2701; Tushare still lists RB2610 until 2026-09-02 |
| Latency SLO | **Not frozen** |
| Live capture / on-call drill | **NOT RUN** |

Likely reason every session hard-gates: Tushare `fut_daily` has no upper/lower
limit fields, so unknown limit risk remains a blocking gate. That is intended
V1 behavior, not a silent pass.

Do not treat this replay as permission to place orders or as production-ready
service. G3 still requires 20 **live-captured** sessions plus completed human
review of the worksheet.
