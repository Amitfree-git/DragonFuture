# 核心正确性修正记录（P01 / DF-010–DF-014）

记录日期：2026-09-05  
基线：`cc899bd491f9f43f7c0f67517229fc0c2460e392`（文档树；源码身份仍对应 `e4fe440`）  
特征版本：`futures_features_v1` → `futures_features_v1_1`  
评分配置版本：`futures_scores_v1`（阈值 YAML 未改；缺失/无效输入的处理变了）

本轮只修可从代码和手算样例证实的缺陷。未接真实数据源，未改 PIT 仓库，未改主力状态机。

`examples/demo_analysis.json` 仍是 **`futures_features_v1` 合成黄金样例**，本轮没有覆盖它。新结果由 `scripts/demo_analysis.py` 在隔离 SQLite 上重跑得到，见下文对照表。

## 审计项与回归测试

| 审计 | 任务 | 回归测试 | 结果 |
|---|---|---|---|
| AUD-01 | DF-010 | `tests/unit/test_rsi.py` | 通过 |
| AUD-05 | DF-011 / DF-012 | `tests/unit/test_limit_risk.py`、`tests/unit/test_missing_critical_risk.py` | 通过 |
| AUD-08（窗口/样本口径相关） | DF-013 | `tests/unit/test_feature_windows.py` | 通过 |
| AUD-02/03/04/06/07/09 及其余 | 不在本轮 | — | 仍开放 |

基线 23 项测试全部保留并通过。本轮新增 12 项（含 Wilder 递推对照与 INVALID 硬门槛），合计 `pytest -q`：**35 passed**。

## 修正前后（合成演示，非真实行情）

同一套 `seed_reference_market` 合成 RB 数据。旧值来自仓库内 `examples/demo_analysis.json`；新值来自本轮代码重跑（输出未写入仓库）。

| 字段 | `futures_features_v1`（保留文件） | `futures_features_v1_1`（本轮重跑） |
|---|---|---|
| `rsi_14` | 100.0 | 93.3206857610545 |
| `volume_zscore_20d` | 1.4043250151669695 | 4.618293872231093 |
| `opportunity.entry_quality` | 26.0 | 35.3510399345237 |
| `opportunity.score` | 56.576195679366975 | 58.86631918855687 |
| `direction.score` | 76.96622666676399 | 76.86036783467283 |
| `opportunity.action` | `wait_for_pullback` | `wait_for_pullback`（未变） |
| `risk.score` | 28.043228222086288 | 28.043228222086288（未变） |
| `price_limit_proximity_risk` | 0.0 | 0.0（该样例未触及涨跌停） |
| `feature_set_version` | `futures_features_v1` | `futures_features_v1_1` |
| `core_result_hash` | `37bcdbca706f29515a51aadbdf5b8b4c16134b98d8933adbadecca1a70c854f1` | `f928392fb28c9fa1eaf91026c9cda0a470b749931e3552b4ab9aba044759cffc` |

RSI 从 100 降到约 93.32，是因为演示序列并非「窗口内全涨」，旧实现把零变化日从均值分母里丢掉，Wilder 初始平均会把这些日计为 0 涨/0 跌。成交量 zscore 变大，是因为名称中的 20 日窗口此前实际用了 60 日历史。

## 公式与边界

### DF-010 Wilder RSI

旧：对非零涨列表、非零跌列表分别求均值，忽略窗口内零变化次数。审计反例（13 涨 + 1 跌）输出 50.0。

新：对完整窗口的 gain/loss（含 0）做 Wilder 初始平均，再递推。同一反例为 `92.85714285714286`（`100 - 100/(1+13)`）。全涨 100、全跌 0、全平 50。

### DF-011 涨跌停

触及上限或下限：接近风险 = 100。越界：`DataStatus.INVALID`，不把越界价当「远离涨停」。上下限缺失：`MISSING`。

### DF-012 关键缺失硬门槛

`liquidity_quality_score` 或 `price_limit_proximity_risk` **出现但不可用**（missing/invalid/无值）时，风险引擎加 `unknown_*` 硬门槛。机会引擎不再把缺失流动性填成 50，也不再把缺失 RSI/ATR 填成 50/0。质量评估若有 `blocking_issues`，分析动作强制为 `insufficient_data`。

为保持旧单元测试（未提供这两项指标）行为，**字典中完全没有该键时不视为未知硬门槛**。完整特征引擎总会写出这两项。

### DF-013 窗口与样本

- `volume_zscore_20d` 使用 `volumes[-21:-1]`（20 日历史），不再用 60 日。
- `realized_volatility`：窗口内任一非正或非有限价格 → `None`；有效对数收益数必须等于 `period`。
- 平坦 MA：价格相等贡献 0，不再自动记 -30 偏空。零 MAD 历史仍回退到 `pstdev`，两者皆退化时 zscore 为 0。

### DF-014 版本与黄金样例

特征集版本升到 `futures_features_v1_1`。旧演示 JSON 仍可读，不能当作本轮输出。缓存身份含 `feature_set_version`，新旧结果不会互相覆盖。

## 验证命令

环境同 [baseline.md](baseline.md)。退出码均为 0。

```text
pytest -q
python -m compileall -q src tests examples scripts alembic
# 隔离临时 SQLite
alembic upgrade head && alembic check && alembic downgrade base && alembic upgrade head
```

无 Schema 迁移。回滚：还原本 PR，继续使用 `futures_features_v1` 与旧演示 JSON。

## 本轮未做

真实数据采集、数据契约/日历 Schema、主力确认与生效映射、连续序列收益口径、失效状态机、历史回放、LLM、生产发布。AUD-02 至 AUD-04、AUD-06、AUD-07、AUD-09 至 AUD-12 仍开放。系统不是生产可用研究服务。
