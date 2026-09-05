# 数据契约（P02 / DF-020–DF-025）

文档日期：2026-09-05。本文件约定真实数据含义、时间和来源，不声称已经取得全部供应商授权或历史 vintage。

首个落地品种默认 **RB（上期所螺纹钢）**。AU / M / SC 先登记字段与缺口，采集在 P03 按实际可用权限扩展。

## 1. 数据模式

| 模式 | 用途 | `available_at` | 严格 PIT |
|---|---|---|---|
| `live_capture` | 按本系统当时知识面回放 | `max(published_at, received_at)` | 是 |
| `historical_vintage` | 有可核验的历史发布时刻 | `published_at`（缺失则拒绝，不编造） | 是 |
| `final_only` | 只有最终修订 | 有 `published_at` 则用之，否则 `received_at` | 否 |
| `estimated` | 估计发布时刻 | 必须显式给出估计或发布时间 | 否 |

G2 严格 PIT 在缺少 historical vintage 时保持 **BLOCKED**。`final_only` 只允许探索，不得宣传已消除修订偏差。

四种时间：`trading_date`（交易所归属日）、`published_at`（来源首次发布）、`received_at`（本系统收到）、`ingested_at`（入库）。API 时间必须带时区，存储为 UTC。

## 2. 品种字段盘点（Tushare 实测 + 缺口）

Tushare 当前可用：`fut_basic`、`fut_daily`、`fut_holding`、`fut_wsr`、`fut_mapping`。分钟线无权限。涨跌停不在 `fut_daily`。实时快照走 Wind，不在本阶段日频边界内。

### 2.1 日行情 `fut_daily` → `fut_bar_daily`

| 字段 | 单位 | 更新 | 缺失策略 | RB | AU | M | SC |
|---|---|---|---|---|---|---|---|
| `trade_date` → `trading_date` | 交易所日 | 日终 | 缺则丢弃 | 有 | 有 | 有 | 有 |
| `open/high/low/close` | 报价单位 | 日终 | 缺则丢弃 | 元/吨 | 元/克 | 元/吨 | 元/桶 |
| `settle` → `settlement` | 同报价 | 日终 | **缺则丢弃，禁止用 close 填充** | 有 | 有 | 有 | 有 |
| `pre_settle` | 同报价 | 日终 | 允许空 | 有 | 有 | 有 | 有 |
| `vol` | 手 | 日终 | 缺则丢弃；0 手合法 | 有 | 有 | 有 | 有 |
| `oi` | 手 | 日终 | 缺则丢弃 | 有 | 有 | 有 | 有 |
| `amount` → `turnover` | Tushare 万元，入库×10000 为元 | 日终 | 允许空 | 有 | 有 | 有 | 有 |
| 涨跌停 | 报价 | — | Tushare 无；保持 NULL，风险层按缺失硬门槛 | 无 | 无 | 无 | 无 |

夜盘已由 Tushare 归到下一交易日，入库不再平移日期。本系统日历仍要能把本地时刻映射到交易所 `trading_date`（见第 4 节）。

### 2.2 合约主数据 `fut_basic`

| 字段 | 本库 | 规则 |
|---|---|---|
| `fut_code` | `symbol` | RB / AU / M / SC |
| `exchange` | `exchange` 全称 | SHF→SHFE，ZCE→CZCE，CFX→CFFEX |
| `symbol`/`ts_code` 主体 | `contract_code` | 如 RB2701，不含后缀 |
| `list_date` | `listed_date` | 允许空 |
| `delist_date` | `last_trade_date`；`expiry_date` 若无独立交割日则与之相同并在文档标明 | 二者不混用语义 |
| `last_ddate` | 不入库为到期日 | 最后交割日，V1 不参与主力筛选 |
| `d_month` | `delivery_month` | YYYYMM |
| `multiplier` | `fut_contract_spec.multiplier` | 实测空值不得写成 0 |

许可证：Tushare 令牌只存在本地环境变量，不进仓库。原始响应只写受控 `storage_uri`，Public 仓库只保存散列。

## 3. Source policy 与批次

读取顺序：source policy 过滤 → `available_at <= as_of` → 业务键内最新可见修订 → 交易日窗口。不同供应商不得仅凭到达更晚互相覆盖。

`fut_data_manifest` 固定 source_policy、data_mode、记录/元数据散列。`pending` 批次不可读；`commit` 后可读。相同 `provider + request_digest + response_hash` 的原始存档重入不新增行。

无 product rule 的品种禁止形成生产候选。`tradable_until` 取 `last_trade_date`（或规则覆盖），不以“到期前统一 7 天”代替交割规则。

## 4. 日历

交易日由版本化 `fut_calendar_day` 决定。夜盘（上期所金属默认 21:00–23:00 上海时区）归属下一交易日；周五夜盘归属下周一（若周一为交易日）。日历修订按 `available_at` 做 PIT：后到来的节假日更正不改变过去 `as_of` 的可见日历。

当前仓库只带 weekday 测试日历，**不是**交易所正式公告节假日文件。正式日历版本在取得公告/授权后另 PR 导入。

## 5. Schema

增量迁移 `c3f8a1b2d904`，前置 `d5ad33d0aea4`，不改初始迁移正文。旧行 `data_mode` 为空时按 `final_only` 解释。无 Schema 回滚风险以外的数据重写；回滚本迁移即去掉新表和新列。
