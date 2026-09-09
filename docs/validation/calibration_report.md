# Calibration / replay report

Status: **synthetic only**. No committed historical vintage was available, so this
does not satisfy G2.

| Item | Result |
|---|---|
| Replay tool | `scripts/replay_history.py` plus `research/replay.py` |
| Online vs replay identity | Same `core_result_hash` for the same as_of |
| Future bar perturbation | Bars with `available_at` after as_of do not change the past hash |
| Labels | 5/20/60d research-index returns start at the **next session**, not the signal close |
| Walk-forward | Train / validate / test are sequential with an embargo; overlapping labels are purged |
| Costs / Sharpe as strategy PnL | **Not reported.** No fill, fee, or roll-cost model is attached |
| Real vintage / PIT certification | **NOT RUN** |

Do not treat a passing unit test as evidence that the rules have sample-out-of-sample edge.


## Audit remediation update 2026-09-05

The prior statement about purging was too broad: the old function merely spaced dates. The corrected split now reserves the maximum label horizon (60 sessions by default) plus the next-session offset at both boundaries. Boundary purging requires `ordered_sessions` and `cutoff`. Without a cutoff it only forms disjoint descriptive windows. The replay CLI now requires an explicit migrated database and attaches labels from persisted same-contract research-index vintages; missing interior points invalidate a label. These engineering corrections are not G2 research acceptance.
