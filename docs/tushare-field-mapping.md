# Tushare 日行情字段映射

盘点日期：2026-09-05。本仓库是独立的 DragonFuture 工程，不是 DragonBoatAI 单体。本地 `a-share-mvp` 没有可复用的期货主数据表、日线表或连续合约表，因此 V1 行情写入本包已有的 20 张表，不新建语义重复的主数据。

## 交易所代码

Tushare `ts_code` 后缀不是交易所全称。写入 `fut_instrument.exchange` 时使用全称。

| 交易所 | Tushare 后缀 | 本库 `exchange` |
| --- | --- | --- |
| 上期所 | SHF | SHFE |
| 郑商所 | ZCE | CZCE |
| 中金所 | CFX | CFFEX |
| 大商所 | DCE | DCE |
| 上期能源 | INE | INE |
| 广期所 | GFE | GFEX |

## 合约主数据 `fut_basic` → 领域对象

| Tushare 字段 | 本库字段 | 语义 |
| --- | --- | --- |
| `fut_code` | `fut_instrument.symbol` | 品种代码，如 RB |
| `exchange` | `fut_instrument.exchange` | 交易所全称 |
| `name` | `fut_instrument.name` | 仅作展示；品种名可能来自首个合约 |
| `symbol` / `ts_code` 主体 | `fut_contract.contract_code` | 如 RB2701，不含后缀 |
| `list_date` | `fut_contract.listed_date` | 上市日 |
| `delist_date` | `fut_contract.last_trade_date` 与 `expiry_date` | 摘牌/最后交易日。`days_to_expiry` 用这一天，不用 `last_ddate` |
| `last_ddate` | 不入库 | 最后交割日，V1 不参与主力筛选 |
| `d_month` | `fut_contract.delivery_month` | YYYYMM |
| `multiplier` | 不入库 | 实测螺纹钢为 null，不能当 0 |

## 日线 `fut_daily` → `DailyBar` / `fut_bar_daily`

| Tushare 字段 | 本库字段 | 语义 |
| --- | --- | --- |
| `trade_date` | `trading_date` | 交易所交易日。夜盘计入次一交易日，Tushare 已经按此归并，入库不再平移日期 |
| `open` / `high` / `low` / `close` | `open_price` / `high_price` / `low_price` / `close_price` | 收盘价不是结算价 |
| `settle` | `settlement_price` | 结算价。缺失则整行丢弃，不得写成 0 |
| `pre_settle` | `previous_settlement` | 前结算 |
| `vol` | `volume` | 手。缺失则整行丢弃，0 手是合法成交 |
| `oi` | `open_interest` | 手。缺失则整行丢弃 |
| `amount` | `turnover` | Tushare 单位是万元，入库乘 10000 转为元 |
| 无 | `upper_limit` / `lower_limit` | Tushare `fut_daily` 无涨跌停，保持 NULL |
| 固定 `tushare` | `source` | 数据源标识 |
| SHA-256(payload) | `payload_hash` | 相同 payload 不重复写；不同 payload 追加 `revision_no` |

时区：`Asia/Shanghai`。本阶段按 `final_only`：`available_at` / `published_at` 取该 `trading_date` 的 16:00（日盘结束后结算可见）。Tushare 无历史 vintage，不能当作 `historical_vintage` 严格 PIT。修订行的 `available_at` 取实际观察到修订的时间。

## 曲线与连续合约

同一 `trading_date` 下至少两个真实合约的结算价、成交量、持仓量组成一条 `fut_curve_snapshot`。点必须属于同一 snapshot，不能跨日拼接。

连续合约不直接使用 Tushare `fut_mapping`。Tushare 主力切换日（例如 RB 在 20260901→20260902 从 RB2610 切到 RB2701）与持仓量确认规则并不相同。本库用 `LiquidityConfirmedMainContractPolicy` 在已完成的曲线快照上决策，**下一交易日生效**，再用已有的后向加法构造 `fut_continuous_bar_daily`，并保留 `source_contract`。

`fut_mapping` 只适合人工对照，不能当 point-in-time 主力真相。

## 现有库盘点结论

| V1 需要的数据 | DragonBoatAI / a-share-mvp | 补采方案 |
| --- | --- | --- |
| instrument / contract master | 无 | `fut_basic` → `fut_instrument` / `fut_contract` |
| contract daily bars | 无 | `fut_daily` → `fut_bar_daily` |
| settlement / previous settlement | 无 | `settle` / `pre_settle` |
| volume / open interest | 无 | `vol` / `oi` |
| upper / lower limit | 无 | Tushare 无此字段，保持缺失 |
| continuous bars | 无 | 由曲线 + 主力政策本地构造 |
| roll events | 无 | 下一交易日生效的切换写入 `fut_roll_event` |
| curve snapshots | 无 | 同日真实合约截面 |
| available_at / revision_no | 无 | 按上面的发布时点规则生成 |

实时快照、分钟线、仓单、持仓龙虎榜和行业库存不在 V1 日频边界内。
