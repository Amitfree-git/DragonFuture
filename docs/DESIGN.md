# DragonFuture 系统详细设计

文档版本：1.0.0｜日期：2026-09-05｜状态：工程设计基准，待实施项不代表已上线

代码基线：`e4fe4401281ee7ad069e5996a4cebf7e51dcaaa2`，Python 包版本 `0.1.0`。

本设计对应独立仓库 `Amitfree-git/DragonFuture`，保留导入路径 `dragonboat_ai.futures_agent`。当前实现、待修正行为和目标设计必须分开阅读；代码核查见 [基线审计](BASELINE_AUDIT.md)，任务顺序见 [实施计划](IMPLEMENTATION_PLAN.md)。本文中的权重、阈值和性能目标均为项目配置或待验证目标，不是交易所规定，也不是已经证明有效的交易策略。

## 1. 目标、使用场景与边界

提供日线、中低频期货市场状态分析，面向研究人员及 Strategy、Portfolio、CIO 等下游服务。一次请求回答：市场状态是什么、方向证据如何、候选机会质量如何、证据是否充分、有哪些风险、什么条件使判断失效。

首批验证候选是 RB、AU、M、SC，分别覆盖黑色、贵金属、农产品、能源；只有完成数据和规则验收的品种才能进入生产白名单。`swing` 表示研究窗口约 5–20 个交易日，`position` 约 20–120 个交易日，不承诺在该窗口获利。

V1 不提供订单执行、账户接入、杠杆与仓位分配、实盘止损指令，也不引入 Tick、Level-2、分钟数据、新闻交易、天气预测或黑箱 ML。先形成独立可回放服务，再通过适配层接入 DragonBoatAI；并入其主仓库不是第一阶段的前置条件。

## 2. 当前基线与目标版本

| 能力 | 0.1.0 基线 | 下一版目标 |
|---|---|---|
| 核心领域模型 | Pydantic 模型及分数边界存在 | 补齐跨字段约束、深层不可变和有限数校验 |
| 数据库 | SQLite、20 张 ORM 业务表、Alembic 初始迁移 | 增量扩展 PIT 元数据、批次、序列快照，不改写旧迁移 |
| 日行情/曲线读取 | 按 available_at 选择可见修订 | 固定数据源策略、批次快照和完整交易日校验 |
| 主力/连续合约 | 连续确认、加法后复权参考算法 | 有状态生效映射、快照版本及独立收益序列 |
| 特征与评分 | 29 个演示指标、4 个方向因子、规则引擎 | 先修复公式和风险缺口，再校准 |
| 失效条件 | 条件生成及单点比较 | 真正跨越事件、连续交易日计数和状态留存 |
| 叙事 | 模板和 LLMNarrativeGenerator 接口 | 全字段论据校验、超时、审计、独立持久化 |
| 外部集成 | 合成 RB 数据演示 | 授权真实数据、历史回放、影子运行及下游协议 |

源码依据：[应用编排](../src/dragonboat_ai/futures_agent/application/analyst.py)、[特征](../src/dragonboat_ai/futures_agent/features/engine.py)、[ORM](../src/dragonboat_ai/futures_agent/infrastructure/database/models.py)。23 项基线测试通过不等于完整 PIT 证明或策略有效性证明。

## 3. 架构不变量

| 编号 | 必须保持的约束 |
|---|---|
| INV-01 | 请求只使用在 as_of 时已知且符合数据模式的事实，包括合约规格、交易日历、修订和移仓决策。 |
| INV-02 | 真实合约、图表连续价、研究收益指数、实际交易损益是四种不同对象。 |
| INV-03 | Direction、Opportunity、Confidence、Risk 分开；高方向分不能绕过风险阻断。 |
| INV-04 | Missing/Invalid/Unknown 不等于中性或安全；关键风控输入缺失时禁止候选。 |
| INV-05 | 指标、评分、状态和失效规则由确定性代码产生；LLM 只能解释。 |
| INV-06 | 相同事实快照、策略配置及核心代码身份必须得到相同核心结果。 |
| INV-07 | 所有结论可追溯至指标、原始记录版本和来源；修订追加，不覆盖历史。 |
| INV-08 | 本服务不拥有执行凭证，也不直接调用交易执行服务。 |
| INV-09 | 主力选择的观测时点、决策时点、生效交易日分开；不使用当日最终数据参与当日盘中选择。 |
| INV-10 | 置信度是证据质量评分，不是胜率；期限结构不是保证兑现的展期收益。 |
| INV-11 | 确定性结果先成功保存；叙事超时、失败或被拒绝不得丢失核心结果。 |
| INV-12 | 历史最终数据重建与真实历史时点数据必须标注为不同验证模式。 |

## 4. 组件与调用顺序

```text
Provider Adapter -> Raw Archive -> Normalize / Validate -> Committed Data Batch
                                                      |
AnalysisRequest -> PIT Context / Manifest -> Data Quality Gate
                    |                            |
                    |                     blocked / unknown result
                    v
Feature Engine -> Factor Engine -> Regime + Direction + Confidence
                    |                              |
                    +--------------------------> Risk Gate
                                                   |
                                             Opportunity
                                                   |
                                        Invalidation Conditions
                                                   |
                                      Core JSON + Evidence -> DB
                                                   |
                                     Template / LLM Narrative
                                                   |
                                           API / Agent Event
```

分层规则：`domain/` 不依赖数据库、网络或 LLM；`ports/` 声明边界；`application/` 编排；`features/`、`scoring/`、`regime/`、`invalidation/` 只使用冻结上下文；`infrastructure/` 实现存储/采集。后续新增采集模块与回放模块，不把供应商 SDK 导入计算核心。

当前主接口是同步 `FuturesMarketAnalyst.analyze(AnalysisRequest)`，不是异步接口。先保持同步核心，批处理和叙事可由外层作业管理；不为日线 V1 预先部署复杂消息集群。

## 5. 六大领域输出与证据模型

| 对象 | 语义、数值范围和约束 |
|---|---|
| MarketRegime | primary、secondary、volatility_regime、liquidity_regime、hypothesis_labels；未知不能写成 normal。 |
| Direction | score ∈ [-100,100] 或 null，带 horizon、label、有效因子权重；不表示概率。 |
| Opportunity | score ∈ [0,100]，action 为候选/等待/no_trade/insufficient_data；不表示订单。 |
| Confidence | score ∈ [0,100]，包含覆盖、及时性、一致性、数据质量；校准项可空。 |
| Risk | score ∈ [0,100]，硬门槛、风险项目、缺失输入和解释；目标增加完整度与 unknown 状态。 |
| Invalidation | 绑定原始 analysis_id 的条件及后续状态；保留评价所用指标版本和交易日。 |

`MetricObservation` 保存 value、unit、normalized_score、lookback、percentile、zscore、observation_time、available_at、source、status、quality_score。目标增加有效样本数、参考窗口首尾、输入记录 ID、normalization_version；样本数指实际用于该运算的样本，而非整段行情总长度。

`Evidence` 区分：fact 是观测或确定性数值；inference 是规则解释；hypothesis 是待证假说。“库存下降”需要库存数据，“该结构偏多”是模型推断，不能因为指标由程序算出就把交易含义标成事实。持仓量变化不识别主动交易方，参见 [S4]。

生产跨字段约束：关键数据阻断 => 方向不可用或明确仅供诊断、Opportunity 不可为候选；任何 hard_gate => no_trade；未知风险不可默认低风险；中性方向的 side 为 none；文本结论不能覆盖结构化动作。现有模型尚未完整实现这些联动。

## 6. 数据契约与时点语义

### 6.1 事实字段

| 数据 | 最小字段 | 关键规则 |
|---|---|---|
| 品种 | exchange、symbol、currency、timezone、canonical_id | 主键含交易所；保留供应商原码。 |
| 合约 | contract_id、instrument_id、listed_date、last_trade_date、expiry_date、delivery_month | 不用字符串猜真实到期日；last_trade_date 与 expiry_date 不混用。 |
| 规格 | multiplier、tick_size、unit、margin/limit rule、valid_from/to、published_at | 生效时间和发布时间都必须建模。 |
| 日行情 | OHLC、settlement、previous_settlement、volume、OI、turnover、上下限 | close 与 settlement 不互相填充；价格单位、OI 单双边口径明示。 |
| 日历 | exchange、session_id、trading_date、open/close、夜盘归属、版本 | 交易日由版本化日历映射，不能简单按自然日或加一天处理。 |
| 曲线 | snapshot_id、交易日、价格类型、所有有效曲线点及各点血缘 | 不拼接不同交易日、时刻或价格类型的合约。 |
| 原始存档 | provider、请求摘要、响应散列、received_at、许可证标识 | 私有原始数据不提交 Public 仓库。 |

### 6.2 四种时间与三种模式

`trading_date` 是交易所归属日；`published_at` 是来源首次发布时刻；`received_at` 是本系统收到时刻；`ingested_at` 是存储时刻。`available_at` 是按数据模式确定的可使用时刻，而非随意把历史日期改成 16:00。

* `live_capture`：按实际系统知识面回放，available_at 不早于 received_at；同时保留 published_at。
* `historical_vintage`：有可核验的历史版本和发布时刻，按当时公众可见版本研究；与本系统实际收到时间分列。
* `final_only` / `estimated`：只有最终修订值或估计发布时刻。允许探索，但不计入严格 PIT 验收，不声称消除了修订偏差。

API 时间必须带时区；存储/散列统一 UTC，展示按市场时区。业务日期由交易日历决定，不用 `as_of.date()` 代替中国市场日期。缺失 publication vintage 不能通过补填字段“修复”。

### 6.3 PIT 读取契约

在同一已提交数据快照中：先按交易所/品种/合约及预定 source policy 过滤，再过滤 `available_at <= as_of`，再在业务键内选择可见修订，最后按交易日截取窗口。修订排序需稳定，并保留源版本号和内部版本号；不允许不同供应商仅凭到达更晚就互相覆盖。

行情、曲线、规格、日历、roll mapping 均纳入 `data_manifest`。Manifest 固定批次 ID、记录版本/散列、最大可见时间、源策略、元数据版本和序列版本。读上下文过程中新增批次不能混入半套新数据。未 committed 的批次不可见；失败批次可重试且不得重复入库。

### 6.4 数据质量

硬阻断：重复/冲突业务键、未知交易日或关键规格、非法非有限数、负 volume/OI、OHLC 次序异常、关键行情缺失/过期、未经支持的价格域、缺少涨跌停或交易资格信息且无法安全判断。对可能出现非正价格的品种必须声明模型支持域，不能把所有负价当数据错误，也不能悄悄删除该日收益。

质量评分用于解释，但不能用高平均分抵消单个硬阻断。及时性按每个依赖来源及预期发布周期检查；周末无新行情不等于故障，新鲜合约数据也不能掩盖陈旧连续序列。

## 7. 主力合约选择

目标是有状态映射，不是每次取最近两个榜首。输入为已完成交易日的真实合约 OI/volume、已知规格、上次 incumbent、版本化资格政策和交易日历。

1. 在 D 日决策时点仅使用已经可见的候选集合，排除不合格或流动性不足合约。
2. 依 OI、volume、到期排序，最后用规范合约代码打破平局。
3. 挑战者须连续 N 个完整交易日满足规则；缺失或不合格日不得被跳过后视为连续。
4. 保存 decision_time、effective_trading_date、from/to、确认证据和 policy_version；D 日收盘后决定最早在下一交易日生效。
5. 生效前继续使用旧映射；原合约不合格时走显式 emergency_roll 或 block，不无声替换。

默认 N=2、成交量/OI 占比 15%、DTE 排除 10 天只是基线启发式。生产规则按品种、最后交易日、交割资格和账户适用限制配置，并经业务确认。显式指定合约绕过自动选择，但不绕过风控。

## 8. 连续序列、收益序列和实际损益

### 8.1 图表价格

加法后复权在历史价上加以后各次移仓价差，适合有明确快照身份的图表和部分价差型研究；不得直接将其百分比收益当成可交易收益。例：100→110 为 10%，整体加 100 后 200→210 仅 5%。若同一历史行随未来移仓重算，必须生成新 `series_snapshot_id`，不能覆盖旧快照。

### 8.2 研究收益指数

下一版对正价格域采用同一真实合约的相邻交易日收益：

```text
c_t = 在 t 日开盘前已生效的研究合约映射
r_t = settlement(c_t, t) / settlement(c_t, t-1) - 1
I_t = I_(t-1) * (1 + r_t), I_0 = 100
```

换月日分子和分母都用新合约，消除跨合约价差的机械跳变。前一日新合约价不可得时不得拼接旧合约价；标记缺失或按预先冻结的替代规则处理。该指数只是研究基准，不含滑点、手续费、保证金收益和真实移仓成交，不等于策略 PnL。非正价格采用单独点值变化模型，否则阻断对应收益特征。

### 8.3 当前合约价格位置

基差、曲线、OI、流动性和限价距离使用真实合约。EntryQuality 的价格、MA 和 ATR 必须来自同一选定合约、同一日期、同一价格口径。品种级长期趋势与指定合约的短期入场位置可同时提供，但必须分别标注，不把研究指数的“价格”当支撑位。

## 9. Feature Engine 详细口径

当前实现：[engine.py](../src/dragonboat_ai/futures_agent/features/engine.py)、[statistics.py](../src/dragonboat_ai/futures_agent/features/statistics.py)。下表区分可沿用定义和必须版本化修正的定义。

| 特征组 | 公式/窗口 | 最少有效样本及修正要求 |
|---|---|---|
| return_5/20/60/120d | 研究指数 I_t/I_(t-h)-1 | h+1 个连续有效交易日；非正或断档不得删日后缩窗。 |
| 波动率调整收益 | 100*tanh(log(I_t/I_(t-h))/(1.5*sigma_d*sqrt(h))) | sigma_d 是20个日对数收益样本标准差；零波动有独立规则。 |
| MA20/60、结构 | 均线与斜率 | MA60 至少60价，5日斜率至少65价；相等应贡献0而非空头。 |
| 区间位置 | (I_t-min(I))/(max(I)-min(I))，120日 | 平坦区间0.5；名称是区间位置，不是假称突破事件。 |
| RSI14 | 下一版明确采用 Wilder 初始化及平滑 | 首14个变化按完整14日计算；需冻结预热规则。 |
| 动量加速度 | R5-R20/4，按5日波动标准化 | 21价及有效波动窗口；启发式而非独立收益预测。 |
| TR/ATR | TR=max(H-L,abs(H-P_prev),abs(L-P_prev)) | P_prev 明确为前收盘或前结算；项目两种口径分名。 |
| ATR-relative extension | (P_t-MA20)/ATR20 | 使用同一真实合约；ATR20基线是TR简单均值，不称Wilder ATR。 |
| OI变化 | OI_t/OI_(t-5)-1 | 6日真实合约，分母为0则missing。 |
| 成交量异常 | Robust Z(volume_t,历史窗口) | 当前名为20d但代码可用60条，下一版统一名称/窗口。 |
| 曲线斜率 | log(F_near/F_far)*365/(DTE_far-DTE_near) | 同快照至少2个合格点、正价、正期限差。 |
| 曲率 | 前两段年化斜率之差 | 同快照至少3点；不把正曲率普遍解释为看多。 |
| 实现波动率 | stdev(日对数收益)*sqrt(A) | RV20=21价，RV60=61价；A=252为配置约定。 |
| 历史分位 | 严格早于本次观测的有效历史中位秩 | 参考窗口、有效n必须输出；不足即insufficient。 |
| 流动性 | 成交/OI分位、品种份额、绝对门槛 | 分母是完整合格合约集合；不能只用2个曲线点算市场份额。 |
| 移仓/限价风险 | DTE、资格、实际上下限和价格距离 | 触及边界距离为0；越界隔离；缺失不可安全默认。 |

RSI 目标算法：`gain=max(delta,0)`、`loss=max(-delta,0)`；初值分别对全部14个变化求均值，以后 `avg_t=(13*avg_(t-1)+value_t)/14`。只有涨无跌=100，只有跌无涨=0，全平=50。完整14次变化“13次+1、1次-1”初值应为92.857142857；现有代码返回50，必须先改并更新特征版本。参考实现对照见 [S5]，这条数值由上述公式直接计算。

标准化采用 `S_percentile=2*p-100`（p为0–100）及 `z=(x-median)/(1.4826*MAD)`、`S_z=100*tanh(z/2)`。MAD退化时是否退回标准差、全常数样本输出何种状态，必须固定配置。不得把“负收益高于历史中位数”直接变成正动量；经济方向和相对异常程度分别存放。

## 10. 期限结构的比较范围

基线取 DTE 最小的两个正期限合约；生产需增加最小流动性、到期排除、最小期限差及合约对标识。历史比较按相同合约选择政策和可比较期限桶建立，不能把换月产生的合约对变化当作曲线突然增强。固定期限插值只能在已观测期限内，并保存方法/权重，不外推未知价格。

正斜率表示近月较贵（Backwardation），负值表示远月较贵（Contango）。Regime 标签必须读原始斜率，不用综合 Curve Score 代替事实符号；change 缺失时只能报结构，不能报“增强”。曲线存在储存、融资、季节性和风险溢价等解释，V1只作启发式证据，不输出确定展期收益或库存紧张事实。

## 11. 方向因子与评分

### 11.1 基线权重

| 因子 | 内部特征权重 | 因子最低覆盖 |
|---|---|---:|
| Trend | R20 .30、R60 .30、R120 .15、MA结构 .15、120日位置 .10 | 60% |
| Momentum | R5 .30、R20 .30、RSI .20、加速度 .20 | 70% |
| Positioning | positioning_composite 1.00 | 80% |
| Term Structure | 斜率 .50、20日变化 .30、曲率 .20 | 50% |

以上来自 [factor_engine.py](../src/dragonboat_ai/futures_agent/scoring/factor_engine.py)，当前两个 horizon 的内部特征权重相同；不是此前草案中分周期的两套 Trend 公式。下一版是否拆分须回放和版本审批。

基线 Positioning：p 是真实合约5日涨跌标准分，o=100*tanh(OI变化/0.05)。增仓时 `sign(p)*(.70*abs(p)+.30*abs(o))`；减仓时 `sign(p)*(.45*abs(p)+.10*abs(o))`；若有成交确认，再以 .90/.10 合并价格方向确认项。只可解释为价仓结构支持，不可识别多空主动行为。

### 11.2 Direction

```text
swing:    Trend .40 + Momentum .25 + Positioning .15 + Curve .20
position: Trend .45 + Momentum .15 + Positioning .10 + Curve .30
D = sum(可用权重*因子分) / sum(可用权重)
```

有效权重达到70%才允许归一化；不足为null。>=60强多，>=25偏多，<=-60强空，<=-25偏空，其余中性。70%恰好通过，边界须有测试。Volatility 无独立方向权重，但可用作收益标准化尺度；这不等于完全不参与方向计算。

Trend 与 Momentum 重用 R20，不能把二者一致当两份独立证据。记录共享 lineage，在回放中做相关性、去重和消融分析；初始权重仅为可解释基准。

## 12. Confidence、Risk、Opportunity

### 12.1 Confidence

基线权重：覆盖 .30、及时性 .20、一致性 .25、数据质量 .15、历史校准 .10。历史校准尚未接入时删除该项并归一化，不填默认50。

当前 freshness 用自然日指数衰减，一致性用与方向相反且绝对分>=20的因子权重。下一版及时性按来源预期发布时点与依赖链评价，一致性明确仅是规则一致性。`72/100` 不能写成“72%获利概率”；生产叙事使用“证据质量评分”。预测概率必须来自另行定义、样本外校准的模型。

### 12.2 Risk

基线软权重为：波动 .30、流动性 .20、roll .15、price_limit .15、crowding .10、数据质量 .10；不是早期草案的 Gap 权重。软风险按可用项归一化，最终 `max(soft_risk,最大硬门槛严重度)`。分档：<30低、[30,60)中、[60,80)高、>=80极高。

生产必须先检查关键风险输入完整性，后算分；关键输入未知直接 block。基线 DTE<7、流动性<20、数据质量<60、限价接近风险>=90为硬门槛，这些均待品种化。仅有日线时只能报告“日终限价距离风险”，不能断言当前盘口可成交；高OI分位仅是待核查的集中度代理，不能证明拥挤多头。

### 12.3 Opportunity

```text
O = clip(.45*abs(D) + .25*EntryQuality + .15*RegimeFit
         + .15*LiquidityQuality - .35*Risk, 0, 100)
```

先验序：数据不可用 > 风险硬门槛 > 置信不足/方向不足 > 价格位置等待 > 候选评分。基线候选门槛45、confidence门槛45、abs(D)门槛25；多头 extension>=2 ATR 或 RSI>=75等待回撤，空头 extension<=-2 ATR 或 RSI<=25等待反弹。具体阈值来自基线，须经回放冻结。

EntryQuality 基线从75起，过度延伸及RSI极值扣分；下一版固定使用真实合约一致量纲，必需指标缺失时不再填“0 ATR/RSI50/流动性50”。long_candidate/short_candidate 只进入策略研究队列，无仓位、无保证金预算、无预期盈亏比承诺。

## 13. Regime 与失效状态机

Primary由Trend分数识别：>=60强多、[20,60)弱多、(-20,20)区间、(-60,-20]弱空、<=-60强空；缺失为unknown/insufficient。Secondary解释趋势-动量冲突、曲线结构和价仓组合。假设标签必须保留possible，不提升为事实。

目标失效状态：`active -> warning -> invalidated`，另设`unknown`、`expired`、`superseded`。`lt`是当日低于，`cross_below`必须满足上次有效观测>=阈值且本次<阈值。若要求“连续两日低于”，应使用lt加streak=2，不能要求连续两日都发生cross事件。

每条规则保存原 analysis_id、condition_id、metric/value_field、阈值、规则版本、last_evaluated_session、streak、first_triggered_at和输入快照。重复处理同一天不得增加streak；缺失数据设unknown并中断连续计数。规则严重度和主条件失效优先于简单“3/5投票”。原结论不原地改写，发布后续失效事件。

## 14. 数据库设计与增量迁移

基线20张表的物理字段由 [ORM](../src/dragonboat_ai/futures_agent/infrastructure/database/models.py) 和 [初始迁移](../alembic/versions/d5ad33d0aea4_futures_agent_v1_schema.py) 定义；以下是职责及关键约束，不另写一套可能漂移的建表SQL。

| 表 | 关键键/内容 | 目标补充 |
|---|---|---|
| fut_instrument | instrument_id；exchange+symbol唯一 | 标识策略和元数据版本 |
| fut_contract | instrument_id+contract_code唯一 | 合约信息历史可见性 |
| fut_contract_spec | contract_id+effective_from唯一；乘数/价位/保证金 | publication时间、来源、版本 |
| fut_bar_daily | contract_id+trading_date+source+revision_no唯一 | received/published/模式、批次一致性 |
| fut_contract_rank_daily | 品种/合约/交易日/计算版本 | 排名快照和有效候选范围 |
| fut_roll_event | 品种/生效日/roll_rule_version | 决策时间、资格政策与确认血缘 |
| fut_continuous_bar_daily | 品种/series_type/日期/calculation_version | series_snapshot_id、原始依赖版本 |
| fut_curve_snapshot | snapshot_id；品种/日期/source/revision | source policy、complete批次 |
| fut_curve_point | snapshot_id+contract_id唯一 | 各点原始bar版本 |
| fut_feature_snapshot | 品种/合约/as_of/horizon/特征版本/input_hash | manifest_id、完整核心代码身份 |
| fut_feature_value | snapshot_id+feature_name | 有效样本数、窗口首尾和质量原因 |
| fut_factor_snapshot | snapshot/因子/模型及配置身份 | 共享证据 lineage |
| fut_analysis_run | request_hash+input_data_hash+version_hash唯一 | 核心/叙事身份拆分、data_mode |
| fut_analysis_evidence | analysis_id+evidence_id | 事实与解释的显式分离 |
| fut_invalidation_rule | analysis_id+condition_id | 版本化规则DSL |
| fut_invalidation_state | 评价状态历史 | 交易日幂等键、streak、unknown |
| fut_data_batch | 来源、状态、计数、metadata_json | committed manifest及原始存档定位 |
| fut_data_quality_issue | 批次/合约/问题/严重度 | 阻断原因与解除事件 |
| fut_model_version | model_type+version唯一 | artifact hash及激活记录 |
| fut_analysis_audit_log | 事件、actor、时间、details | 重试、降级、配置切换审计 |

目标新增概念：exchange_calendar、source_publication、data_manifest、active_contract_mapping、series_snapshot、narrative_run、event_outbox。具体表名在实施PR冻结，不声称已经存在。

迁移采用expand/backfill/validate/switch；原始记录不覆盖。核心分析及其指标/因子/证据在单事务中提交，失败回滚；SQLAlchemy事务边界依据 [S3]。SQLite继续用于单机日线V1，WAL读写并发但只有一个写者，不部署到网络共享文件系统 [S2]。生产持久性配置需明确synchronous策略、备份和断电恢复要求，不把WAL模式等同于绝对不丢数据。

## 15. API、协议与幂等

### 15.1 已实现接口

| 方法/路径（前缀 /api/v1/futures） | 当前行为 |
|---|---|
| GET /health | 进程健康，不是数据就绪证明 |
| POST /analyses | 同步分析；领域错误当前统一422 |
| GET /analyses/{analysis_id} | 结果或404 |
| GET /symbols/{symbol}/latest?horizon=... | 按symbol/horizon查最新；尚未有exchange/as_of过滤 |

请求必须包含symbol、带时区as_of，可选exchange/contract；同symbol存在歧义时拒绝猜测。完整响应以 `FuturesMarketAnalysis.model_json_schema()` 为准。Pydantic `extra=forbid` 和 `frozen=True` 不等同于开启strict模式或深层不可变 [S1]。

目标新增：exchange、contract、as_of-aware latest查询，invalidation状态查询，有限大小batch接口和data readiness。错误区分400语义参数、404对象不存在、422类型验证、409输入快照冲突、503数据源不可用；合法但证据不足的分析返回结构化blocked结果而不是伪造中性分。发布API变更须做兼容测试。

### 15.2 下游事件（待实现）

```json
{
  "event_type": "futures.market_analysis.published",
  "schema_version": "1.0.0",
  "analysis_id": "<persisted-id>",
  "core_result_hash": "<sha256>",
  "as_of": "<UTC-aware-timestamp>",
  "instrument": {"exchange": "SHFE", "symbol": "RB"},
  "contract": "<explicit-contract>",
  "horizon": "swing",
  "data_mode": "live_capture",
  "payload": "<validated FuturesMarketAnalysis core object>"
}
```

上述为协议模板，不是实际API响应。目标由同事务outbox可靠发布，按at-least-once消费和event_id去重；不能承诺网络exactly-once。下游必须读取action和hard_gate，不解析摘要恢复分数。无直接Execution依赖。

### 15.3 三种身份

`request_hash`表示规范化请求，`input_data_hash`表示包括元数据的完整manifest，`core_result_hash`表示核心输出。目标把prompt/model/temperature/include_narrative从核心身份剥离，仅进入narrative身份；当前实现仍把部分叙事参数包含在请求/版本身份中，见审计。

JSON排序、时间统一UTC、数值和Decimal序列化、配置散列、代码artifact身份都须冻结。UUID、生成时刻、日志和叙事不进入核心散列。改变规则参数、归一化或合约映射均生成新版本；force_refresh不绕开PIT、不篡改旧结果。

## 16. 叙事、错误处理与运行安全

模型只接收筛选过的结构化证据；不传账户凭证或不必要的私有原始数据。目标全节使用带evidence_ids/metric_ids的claim对象，区分事实/推断/假设；检查数字、方向、action及引用。不允许输入文本中的指令提升权限。

核心先保存；叙事设超时、一次受控重试和模板回退，单独记录provider/model/prompt版本、请求ID、token用量、错误类。引用ID存在只能证明指向已知记录，不能证明句子被其支持；需要额外语义/数值一致性测试。当前适配器仅校验多头和空头两节的引用。

运行目标：本机API默认127.0.0.1；对外开放前增加鉴权、限流和审计。配置秘钥从环境或凭证库读取，不写入Public源码、示例、日志或CI产物。单写入队列、限次重试、staging隔离、只读降级；源码/依赖版本锁定。日志关联analysis_id、batch_id、manifest_id与error_code，不记录密钥或完整外部响应。

## 17. 验证、发布与后续扩展

工程测试覆盖手算公式、边界、未来扰动、修订、换月、时区、缺失、幂等、并发和失败恢复；研究验证另行覆盖按时间walk-forward、重叠标签隔离、成本敏感性、分品种分桶及样本量。时间切分可借鉴 [S6]，但TimeSeriesSplit本身不会处理所有重叠标签泄漏。

验收目标：PIT未来扰动对过去核心结果零影响；关键缺失场景零候选；同快照核心散列完全一致；参考公式误差在冻结容差内。性能SLO在指定硬件、品种数和窗口长度上测量后冻结，尚无生产性能结论。

发布层级：B0参考实现 -> R1正确性/PIT修正 -> R2真实数据研究 -> R3影子运行与生产只读分析。任何阶段都不是自动交易授权。V2再加入可比口径的现货/基差/库存/季节性；V3才考虑样本外概率模型，且仍与规则风控和执行隔离。

## 18. 外部依据

以下文档核对日期为2026-09-05；仅支持相应工程/指标概念，不构成本项目通过生产验收的证据。

- [S1 Pydantic模型](https://docs.pydantic.dev/latest/concepts/models/) 与 [Strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)：类型校验、序列化和严格模式边界。
- [S2 SQLite WAL](https://www.sqlite.org/wal.html)：并发、单写者与文件系统约束。
- [S3 SQLAlchemy事务](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)：显式事务管理。
- [S4 CME Open Interest](https://www.cmegroup.com/education/courses/introduction-to-futures/open-interest)：持仓量概念。
- [S5 TA-Lib RSI](https://ta-lib.github.io/ta-doc/indicator/RSI.htm)：指标实现对照入口；项目仍须锁定算法版本和初始化。
- [S6 TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)：按时间划分及gap参数。

交易所日历、合约规格、交割/限价规则及供应商许可必须在数据接入PR按品种获取当时有效的原始公告并存档；本设计没有用统一DTE阈值代替这些规则。
