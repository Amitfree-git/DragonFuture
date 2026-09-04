# Codex 后续任务书：真实数据接入与 DragonBoatAI 集成

## 总目标

把当前可独立运行的 V1 参考实现接入 `a-share-mvp/DragonBoatAI`，使用真实 point-in-time 期货数据，在不引入未来函数、不耦合交易执行的前提下，产出可供 Strategy Agent、Portfolio Manager 与 CIO 消费的结构化行情分析。

## 不可破坏的不变量

1. 所有输入必须满足 `available_at <= as_of`。
2. 连续合约只用于 Trend、Momentum；真实合约用于 Positioning、Liquidity、Limits、Term Structure。
3. 缺失数据不是 0 分。
4. Direction、Opportunity、Confidence、Risk 独立。
5. LLM 不参与指标与评分计算。
6. 相同输入哈希、配置版本和代码版本必须产生相同核心结果。
7. Futures Market Analyst 不直接下单。
8. 主力切换决定至少下一交易日生效。

## PR 1：引入模块与统一工程规范

### 工作

- 将本模块以 workspace/monorepo package 或内部依赖接入现有仓库。
- 对齐现有 Python 包管理、日志、配置、依赖注入和测试约定。
- 保留模块边界，不重写核心领域模型。
- 将 CI 加入：
  - `pytest -q`
  - `ruff check`
  - Alembic upgrade smoke test

### 验收

- 当前 22 项基础测试全部通过。
- DragonBoatAI 原有测试不回归。
- `futures-agent-demo` 能从主项目环境运行。

## PR 2：现有数据库盘点与映射

### 工作

盘点以下数据是否已经存在：

```text
instrument/contract master
contract daily bars
settlement / previous settlement
volume / open interest
upper/lower limit
continuous bars
roll events
curve snapshots
available_at / revision_no
```

输出映射文档：

```text
existing_table.field → V1 domain field
```

不得在不确认字段语义的情况下直接映射 `date`、`close` 或 `main_contract`。

### 验收

- 明确每个字段的数据源、时区、发布时点和修订策略。
- 列出缺失数据和补采方案。
- 确认夜盘 `trading_date` 语义。

## PR 3：MarketDataRepository 真实适配器

### 工作

实现：

```text
list_contracts
get_daily_bars
get_continuous_bars
get_curve_snapshots
```

要求：

- 查询参数必须显式携带 `as_of`；
- 同日多修订只返回当时可见的最高修订；
- 按交易所与 symbol 双重过滤；
- 结果按交易日稳定排序；
- Decimal 保留在领域边界，计算层再转 float64。

### 必加测试

```text
test_future_revision_not_visible
test_latest_visible_revision_selected
test_night_session_trading_date
test_exchange_symbol_collision
test_curve_points_are_same_snapshot
test_limit_per_contract_is_applied_after_revision_selection
```

## PR 4：主力合约与连续合约生产构建

### 工作

- 用真实持仓量/成交量实现主力候选排名。
- 排除临近交割和低流动性合约。
- 连续确认 N 日。
- 切换下一交易日生效。
- 构建 raw、unadjusted、back-adjusted 序列。
- 每日保存真实来源合约与复权累计值。

### 验收

- 移仓日不存在人工跳空收益。
- 任一天连续价可追溯至真实合约。
- 用当时已知信息重建历史切换。
- 真实历史 Golden Test 覆盖至少四类品种：黑色、贵金属、农产品、能源。

## PR 5：数据库迁移与持久化

### 工作

- 评估 V1 20 张表与现有 Schema 的复用/新增边界。
- 不重复建设语义相同的主数据表。
- 保留分析运行、指标、因子、证据、失效条件与审计结构。
- 为 SQLite/PostgreSQL 配置分别验证。

### 验收

- 空库可 `upgrade head`。
- 生产样本可完整写入和读取。
- 同一 request hash 不重复写入。
- 一次分析保存发生在单事务内。

## PR 6：Agent Bus / CIO 协议

### 工作

定义：

```text
futures_market_analysis.v1
```

下游只消费结构化字段，不解析叙事文本。

明确：

- Direction 是市场倾向；
- Opportunity 是候选质量；
- Risk 是独立风险；
- `no_trade` 不能被下游当作弱买入/弱卖出；
- Invalidation 需要后续周期性评估。

### 验收

- Schema 有版本号。
- 消费者对新增字段向后兼容。
- 不存在 Futures Analyst → Execution 的直接依赖路径。

## PR 7：历史校准

### 工作

对每个品种和总体进行 walk-forward 回放：

```text
Direction score distribution
Opportunity bucket forward returns
Confidence calibration
Risk bucket max drawdown
Regime persistence
Turnover / roll-period behavior
```

目标变量至少包括：

```text
future_return_5d
future_return_20d
future_return_60d
max_adverse_excursion_20d
max_favorable_excursion_20d
```

仅用于校准和验证 V1 规则，不要在此 PR 引入黑箱 ML。

### 验收

- 严格 point-in-time。
- 训练/校准窗口与验证窗口分离。
- 所有阈值调整升级 `score_config_version`。
- 输出 calibration report，而不是只报告单一胜率。

## PR 8：LLM 叙事接入

### 工作

- 接入 DragonBoatAI 现有模型路由器。
- 使用 `StructuredLLMNarrativeGenerator` 或等价适配器。
- 强制 Pydantic 输出校验。
- 保存 `prompt_version`、模型标识与生成状态。
- 模型失败自动模板降级。

### 验收

- LLM 无法修改核心评分。
- 所有事实性陈述可以映射 evidence/metric。
- inference/hypothesis 使用不确定性语言。
- 不输出直接订单与保证性表述。

## 最终 Definition of Done

- 四类以上真实品种完成至少三年 point-in-time 回放。
- 当前 V1 测试 + 新增真实适配器测试全部通过。
- 主力切换和数据修订不存在未来函数。
- 生产 API 与 Agent Bus 均返回同一 Schema。
- LLM 关闭时核心服务仍可运行。
- CIO 能消费结构化结论，但执行链仍受独立风控约束。
