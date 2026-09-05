# DragonFuture 实施主计划

文档版本：1.0.0｜日期：2026-09-05｜代码基线：`e4fe4401281ee7ad069e5996a4cebf7e51dcaaa2`

设计依据：[DESIGN.md](DESIGN.md)。问题依据：[BASELINE_AUDIT.md](BASELINE_AUDIT.md)。本计划是从当前0.1.0参考实现走向真实数据研究、影子运行和生产只读服务的执行基准，不是“以下功能已经完成”的清单。

## 1. 交付边界与状态约定

此次文档补齐仅增加设计、任务拆解和审计记录；不修改业务代码、数据库、评分参数，不接实盘、不改变仓库权限。源码已经存在的模块应增量修正，不从零重写，也不先强制并入DragonBoatAI。

状态定义：`BASELINE`=旧实现存在但未达到目标；`VERIFIED`=有本次明确检查证据；`PLANNED`=尚未实施；`BLOCKED`=前置资料/规则未满足；`ACCEPTED`=PR、测试和验收产物齐全。GitHub上传成功与业务验收分别记录。

| 交付 | 当前状态 | 证据或限制 |
|---|---|---|
| 0.1.0源码及20张业务表 | BASELINE | main基线及ORM/初始迁移 |
| 代码备份一致性 | VERIFIED | 本地ZIP构造的Git tree与远端均为317b0c6ecd3fe9fcb3692d785961c6abdec8578a |
| 基线23项测试 | VERIFIED | 本次在该备份运行pytest通过；未重测旧覆盖率报告 |
| 本轮设计/计划/审计文档 | 文档交付 | 不代表审计缺陷已修复 |
| 真实数据、PIT元数据、生产主力生效映射 | PLANNED | 不能用合成数据演示代替 |
| 历史校准、影子运行、生产发布、ML | PLANNED | 所有量化验收与实际数据结果均待执行 |

## 2. 依赖关系与发布门槛

```text
P00 基线复现/CI
  -> P01 计算与风险正确性修正
  -> P02 数据契约/日历/时点Schema
  -> P03 真实数据采集与PIT仓库
  -> P04 主力生效映射/连续快照/研究收益
  -> P05 特征与因子版本化
  -> P06 决策/失效/API加固
  -> P07 历史回放与校准
  -> P08 真实数据影子运行
  -> P10 下游集成与生产只读服务
P06 -> P09 LLM叙事（可选，不阻塞纯确定性服务）
P07、P08完成 -> P11 V2基本面；再单独评审ML
```

研究、数据和服务负责人分别签核口径、源授权和运行风险；单人项目也要分开记录这三种检查，不以一个模型的“看起来合理”替代。并行只允许无共享迁移/核心文件冲突的任务，Schema和公式变动由单一PR串行合并。

| Gate | 允许交付 | 必须满足 |
|---|---|---|
| G0 基线可信 | 可继续开发 | 基线命令复现、依赖锁定、审计问题登记 |
| G1 核心正确 | R1研究参考版 | P01-P06的阻断问题关闭，PIT/缺失/状态机测试通过 |
| G2 研究成立 | R2真实数据研究版 | P07完成，数据vintage等级和失效结论透明，无样本外选择污染 |
| G3 影子可靠 | 只读试运行 | P08满足运行标准；不能直接发订单 |
| G4 生产可运维 | R3生产分析服务 | 访问控制、备份恢复、告警、回滚、下游契约验收 |

G2不预设“胜率必须达到多少”作为通过标准；没有可交易增量的因子应降权、删除或保留诊断，而不是反复调参直到样本盈利。回放口径未验证前，不宣传全品种通用有效。

## 3. PR执行总表

| PR | 工作包 | 前置 | 首要交付 | 状态 |
|---|---|---|---|---|
| PR-01 | P00 | 本轮文档 | 可复现环境、CI及基线记录 | PLANNED |
| PR-02 | P01 | PR-01 | RSI/限价/缺失/样本口径修正及回归测试 | PLANNED |
| PR-03 | P02 | PR-01，核心接口评审 | 数据契约、PIT时间、日历和增量迁移 | PLANNED |
| PR-04 | P03 | PR-03 | 原始存档、真实采集、批次与PIT repository | PLANNED |
| PR-05 | P04 | PR-02/04 | 主力状态、生效映射、收益与图表序列分离 | PLANNED |
| PR-06 | P05 | PR-05 | 特征注册表、参考值、因子版本和追溯 | PLANNED |
| PR-07 | P06 | PR-06 | unknown风控、失效状态机、API/散列加固 | PLANNED |
| PR-08 | P07 | PR-07 | 回放工具、校准报告、冻结配置 | PLANNED |
| PR-09 | P08 | PR-08 | 影子运行报告与运行手册 | PLANNED |
| PR-10 | P09 | PR-07 | 可选LLM适配与证据一致性测试 | PLANNED |
| PR-11 | P10 | PR-09，采用LLM时加PR-10 | 事件契约、访问控制、备份与生产验收 | PLANNED |
| PR-12+ | P11 | G4及单独范围评审 | 基差/库存/季节性，再考虑ML | PLANNED |

每个PR必须写明：关联任务/审计ID、设计章节、输入输出、修改文件、迁移、测试、运行结果、失败场景、配置/模型版本、回滚方法。不得把所有阶段塞入一个不可审查的PR。

## 4. P00：工程基线与自动验证

**目标：** 先确认已有实现可复现，保留其限制。输入为0.1.0源码，不需要真实行情。

| Task | 工作与涉及文件 | 验收 |
|---|---|---|
| DF-000 | 记录Python/依赖版本、基线commit/tree；维护requirements lock或等价锁定产物 | 干净环境可安装，lock变动可审查 |
| DF-001 | 配置CI：tests、compile、迁移smoke；lint工具加入dev依赖后才设强制门槛 | PR及push触发；日志可见；无私有数据/凭证 |
| DF-002 | 在临时SQLite文件执行upgrade/check/downgrade/re-upgrade；不操作用户实际库 | 初始20业务表，metadata差异为空，数据目录不入Git |
| DF-003 | 保留旧演示JSON和旧验证报告，增加按commit记录的新基线产物 | 23项测试复现；演示明确synthetic；旧报告不冒充当前结果 |

涉及：`pyproject.toml`、`tests/`、`alembic/`、拟新增`.github/workflows/ci.yml`及`docs/validation/`。无业务Schema变动。输出包含命令、环境、退出码、测试数与artifact hash。

**退出条件：** G0通过，审计AUD-01至AUD-12全部建账；它们可以尚未关闭，但不得遗漏。

## 5. P01：核心计算和风险缺口优先修正

**目标：** 修正已经可以从代码和手算样例证实的缺陷，不借机重写架构。输入为固定合成测试向量；输出新特征/评分版本及变化说明。该阶段先不把现有加法复权收益结果用于真实决策。

| Task | 工作、文件 | 必加测试/预期 |
|---|---|---|
| DF-010 | `features/statistics.py`实现明确的Wilder RSI、完整窗口平均和初始化 | `test_rsi_wilder_initial_13_up_1_down`=92.857142857；全涨100/全跌0/全平50；递推与参考值一致 |
| DF-011 | `features/engine.py`处理上下限等值/越界/缺失，价格参考字段显式 | `test_limit_equality_is_max_risk`、`test_limit_breach_is_invalid`；触及不再返回低风险 |
| DF-012 | `scoring/risk_engine.py`和`opportunity_engine.py`拒绝关键unknown；`application/analyst.py`质量阻断 | `test_missing_critical_risk_blocks_candidate`；无流动性/限价信息不填50；blocking不能产出正常候选 |
| DF-013 | 统一volume窗口名称、有效样本数、零波动、MA相等和非有限输入处理 | `test_volume_window_matches_name`、`test_nonpositive_log_domain_not_silently_dropped`、平坦MA不自动偏空 |
| DF-014 | 对黄金样例展示修正前后差异，更新feature/config版本 | 老版本结果可读；新值不能覆盖旧期望文件并声称未变 |

迁移：尽量无；确需新增质量字段时在PR-03统一承接。输出 `docs/validation/core_correctness.md`。**退出条件：** AUD-01、AUD-05关键阻断、AUD-08相关口径有对应回归测试；旧测试回归不减，新增公式误差目标abs<=1e-9（在参考有效域内）。

## 6. P02：数据契约、日历、来源与时点Schema

**目标：** 先约定真实数据是什么，再写适配器。输入为候选供应商和交易所原始规则；不能把未取得的权限或历史vintage写成已具备。

| Task | 工作、输出 | 验收 |
|---|---|---|
| DF-020 | 按RB/AU/M/SC盘点字段/许可/发布/修订历史；首个品种默认RB但以实际可用数据决定 | 每字段有provider、单位、更新周期、缺失策略；不能用close填settlement |
| DF-021 | 定义live_capture/historical_vintage/final_only/estimated | 真实历史版本不足时标明限制，estimated不通过严格PIT门槛 |
| DF-022 | 增量建模published_at、received_at、available_at、metadata valid/publication时间 | 时区拒绝naive；UTC规范化；到期/规格修订可回放 |
| DF-023 | 交易所日历和夜盘session映射、节假日/临时变更版本 | `test_night_session_exchange_trading_date`、`test_calendar_revision_point_in_time` |
| DF-024 | 设计raw archive、data manifest、source policy、batch committed状态 | 同批次重入无重复；未提交批次不可读；哈希含元数据 |
| DF-025 | 明确last_trade_date、expiry、账户适用资格和tradable_until规则 | 无产品规则时禁止生产候选；不以“统一7天”代替交割规则 |

文件：`domain/market_data.py`、`domain/models.py`、`ports/repositories.py`、`infrastructure/database/models.py`；拟新增`infrastructure/data_sources/`、`contracts/calendar.py`；迁移以现有`d5ad33d0aea4`为前置，不修改初始迁移正文。

输出：`docs/data_contract.md`、字段映射表、许可证/原始公告索引、增量迁移、PIT契约测试。原始商业数据留本地受控路径，Public仓库只提交合法样例和散列。

**退出条件：** 数据含义、时间和source选择可判定。没有vintage可先做final_only探索，但标记G2严格PIT分支BLOCKED，而不是阻止所有工程工作或伪造历史发布时点。

## 7. P03：真实行情采集、批次治理与PIT读取

**目标：** 从首个真实品种完整打通原始事实到可审计上下文，再横向扩展。

| Task | 工作、涉及模块 | 验收 |
|---|---|---|
| DF-030 | ProviderAdapter能力描述：日行情/合约/规格/日历/历史版本覆盖 | 启动输出capabilities；缺少能力显式拒绝，不silent fallback |
| DF-031 | 原始响应存档、字段标准化、去重、修订追加、隔离异常 | 同响应不重复版本；改变旧行情产生新记录及hash |
| DF-032 | 分页、限次重试、超时、断点续采、批次状态 | 限流/断网不产生半完成数据；重跑可恢复 |
| DF-033 | 日行情、曲线、元数据在同manifest内按source policy读取 | `test_latest_visible_revision_per_source`、`test_manifest_read_is_atomic` |
| DF-034 | 同快照真实合约构建曲线，并保留完整市场合约集合 | 曲线点各自来源可追溯；份额分母不缩成2点 |
| DF-035 | 建立交易日覆盖报告及独立来源抽样核对 | 价差按tick容差解释，日期/单位/成交量/OI差异逐项分类 |

输入：P02契约和授权凭证（不得写入库仓源码）。输出：受控原始存档、批次manifest、真实数据Golden样例及缺失/修订报告。文件重点：`infrastructure/database/repositories.py`、`application/context_builder.py`及新增source adapters。

**退出条件：** 任意测试as_of只返回所选模式当时可见记录；新修订加入后过去结果不变；新增未来bars/曲线/规格均不影响过去上下文。尚无生产吞吐结论。

## 8. P04：主力状态、生效日及双序列

**目标：** 完成合同身份与收益口径，不把图表复权当实际回报。

| Task | 工作 | 必加测试 |
|---|---|---|
| DF-040 | incumbent/challenger持久状态、完整交易日连续确认、稳定tie-break | `test_confirmation_breaks_on_missing_session`、`test_tied_candidates_are_deterministic` |
| DF-041 | 保存decision_at/effective_session；自动选择读取已生效映射 | `test_roll_not_effective_on_decision_day`、`test_next_session_respects_holiday` |
| DF-042 | 原合约失去资格时显式emergency_roll/block；只按已知资料决策 | `test_ineligible_incumbent_never_silently_traded` |
| DF-043 | 加法图表序列按series_snapshot_id存档，读取不混合多次构建 | `test_backadjustment_vintage_is_immutable` |
| DF-044 | 同合约收益链接研究指数；真实成交PnL由独立评估模块计算 | `test_roll_gap_not_counted_as_market_return`、`test_chart_rebase_does_not_change_return_index` |
| DF-045 | 指定合约的位置/ATR与品种趋势分开 | `test_explicit_contract_extension_uses_own_scale` |

涉及：`contracts/main_contract_policy.py`、`continuous_series.py`、`application/context_builder.py`、PIT repository，新增映射/序列快照迁移。Golden至少包含有/无换月、假期、切换日新合约缺价、历史修订、非正价格域。

**退出条件：** INV-02/09有全链路测试，任一天映射/图表/研究收益均可追溯；未按真实交易规则建模的roll成本不得伪装为零成本实盘收益。

## 9. P05：特征注册与因子版本化

**目标：** 使每个分数的含义、样本、时间和依赖明确，避免名称与算法漂移。

| Task | 工作、输出 | 验收 |
|---|---|---|
| DF-050 | FeatureSpec登记公式、单位、窗口、min_samples、预热、支持价格域、归一化和依赖 | 一份注册表生成说明与测试参数，29个基线指标逐项映射 |
| DF-051 | 收益/MA/RSI基于研究序列；Entry位置基于真实合约 | 输入series_type错误应fail，而非接受错误量纲 |
| DF-052 | 每项特征保存自身available_at与源数据日期/窗口 | 新鲜合约不掩盖陈旧连续数据；有效n不是总bars数 |
| DF-053 | 曲线合格合约过滤、期限桶/合约对身份和换月变化分离 | `test_curve_change_not_caused_by_pair_switch`；change缺失无strengthening |
| DF-054 | 因子coverage与归一化门槛；共享特征lineage和因子消融 | 69%/70%方向边界、缺失不填0；Trend/Momentum共用证据标识 |
| DF-055 | 生成特征快照、版本清单和参考Golden | 相同manifest/version结果完全一致；配置内容变化使身份变化 |

涉及：`features/`、`scoring/factor_engine.py`、`scoring/config.py`、`domain/models.py`、快照持久化。必要Schema改动包括有效样本数、窗口首尾和lineage字段。

**退出条件：** 所有启用特征有手算或冻结参考值、边界测试、支持域、as_of测试；ADX、基差等未实现项不得出现在“当前可用”清单。

## 10. P06：决策、失效、散列与API加固

**目标：** 将未知和拒绝候选作为正常状态，并提供可被机器安全消费的协议。

| Task | 工作 | 验收 |
|---|---|---|
| DF-060 | data blocked/unknown跨字段约束、关键风险覆盖和硬门槛优先级 | `test_blocked_quality_prevents_valid_direction`、`test_hard_gate_overrides_strong_direction` |
| DF-061 | Confidence标为证据质量；消除missing参数伪装默认中性 | 摘要不出现未校准获利概率；risk unknown不为low |
| DF-062 | 原analysis绑定失效规则、cross事件、streak、unknown与交易日幂等 | `test_cross_requires_previous_observation`、`test_duplicate_session_does_not_increment_streak` |
| DF-063 | 完整manifest哈希；核心与叙事请求/版本/缓存分离 | prompt/include_narrative变化不改核心；calendar/spec变化必须改身份 |
| DF-064 | 核心先落库，叙事独立保存；事务失败、并发唯一键与重试处理 | `test_narrative_timeout_preserves_core`、`test_concurrent_identical_request_is_idempotent` |
| DF-065 | latest增加exchange/contract/as_of过滤，invalidation查询与错误码 | `test_latest_never_returns_future_analysis`、跨交易所隔离、OpenAPI契约测试 |
| DF-066 | bounded batch、readiness及输入上限，保持同步计算核心 | 单项失败不伪装批量全成功；大请求可控拒绝 |

涉及：`application/analyst.py`、`scoring/`、`invalidation/engine.py`、`api/routes.py`、`ports/`、缓存及新叙事/失效状态表。跨字段或错误码变动须更新schema版本和消费者兼容说明。

**退出条件：** G1，所有AUD中P0正确性阻断关闭；LLM禁用时端到端可用，指标到原始事实追溯完整。

## 11. P07：历史回放、研究验证与校准

**目标：** 验证规则是否具有可解释、可重复的样本外信息，不把测试通过等同于策略有效。

| Task | 工作/输出 | 验收 |
|---|---|---|
| DF-070 | `replay(as_of_sequence, manifest_policy, frozen_model)`工具及逐日审计 | 单日回放等于同上下文在线分析；未来数据扰动不影响过去 |
| DF-071 | 按时间walk-forward，训练/校准/验证区间分离 | 标签覆盖到验证区间的训练样本清除；跨品种同日一起分组 |
| DF-072 | 定义5/20/60日标签、MAE/MFE、真实合约切换处理 | next-session最早可执行价格与信号日结算分开，不假设收盘后信息能在此前价格成交 |
| DF-073 | 分品种/时期/状态报告Direction、Opportunity分桶及Risk损失分布 | 展示样本量、缺失率、置信区间、效应方向；无单一胜率摘要代替 |
| DF-074 | Trend-only等简单基准、去掉Curve/OI的消融、成本和参数扰动 | 记录全部尝试，不只挑最佳配置；失败品种可退出白名单 |
| DF-075 | 冻结模型/config/数据manifest，样本外验证不再调参 | 报告可一键复现，同seed/快照/代码hash一致 |

文件：拟新增`research/replay.py`、`research/labels.py`、`research/evaluation.py`、`scripts/replay_history.py`、`docs/validation/calibration_report.md`。只需要标准统计方法，不在此PR引入ML。

数据目标为四类品种尽可能覆盖至少三个完整年及多次换月，但是否具备历史vintage必须单独验证。历史不足可做受限回放，报告不足；仅最终数据回填不能获得严格PIT认证。对重叠h日标签按标签结束时间purge，至少覆盖最大预测窗口；仅使用普通随机交叉验证禁止通过。以日期分组使同日跨品种不泄漏，bootstrap等评估需考虑时间相关性。

收益评估分两层：研究标签是市场变动；可交易代理需额外写明合约数量/名义本金口径、成交假设、手续费、滑点、涨跌停未成交、移仓成本。没有该模型不得发布Sharpe/收益率为“本Agent策略收益”。

**退出条件：** G2。正面、无效和不确定结果都可验收为研究结果；只有证据支持的规则进入影子候选白名单。

## 12. P08：真实数据影子运行

**目标：** 使用实时捕获的日终事实，发布只读报告，不接订单执行。

| Task | 工作 | 验收 |
|---|---|---|
| DF-080 | 数据到齐后按exchange watermark运行，而非硬编码每天固定16:30 | 延迟/修订会降级或重新生成新身份，不提前读结算 |
| DF-081 | 连续记录数据时效、上下文hash、score、阻断原因及人审反馈 | 每日可查原始manifest；缺口无静默处理 |
| DF-082 | 注入断网、缺关键字段、重复批次、陈旧数据、模型超时 | 全部预定故障场景无误发候选，核心结果不丢失 |
| DF-083 | 在固定测试机器记录计算延迟、写锁、批处理吞吐和内存 | 明示硬件/窗口/品种数；根据测量冻结SLO，不虚构性能 |
| DF-084 | 人工复核各品种选约、曲线方向、限价、假设与失效 | 重大错误清零并有回归样例；问题闭环 |

观察目标：至少20个真实交易日、至少一次有记录的修订或故障演练；没有自然发生换月时加入明确标注的历史换月演练，不谎称覆盖了实际换月。20日是项目验收窗口，不是收益有效性的统计证明。

输出：`docs/validation/shadow_report.md`及`docs/runbook.md`。**退出条件：** G3；未满足观察条件只能称实验/试用服务，不宣布生产就绪。

## 13. P09：可选LLM叙事

**目标：** 将解释层接入实际模型路由器，但不影响无LLM模式。

| Task | 工作 | 验收 |
|---|---|---|
| DF-090 | 接入现有`LLMNarrativeGenerator`/`StructuredCompletionClient`，限定输入 | 真实供应商由可用授权决定；不写错现有类名 |
| DF-091 | 全节claim引用、数字白名单/一致性、fact/inference/hypothesis校验 | 引用存在但内容不支持也可被拒绝；方向动作不矛盾 |
| DF-092 | 超时、预算、一次受控重试、模板回退、模型/prompt版本与token日志 | 网络失败后核心仍有记录，重试不重复核心分析 |
| DF-093 | 提示注入、虚构新闻、篡改分数、把confidence写成概率等红队样例 | 所有关键禁止项被测试阻断；不把Prompt文字当安全机制 |

文件：`narrative/llm_adapter.py`、`prompt.py`、`fallback.py`、新narrative记录表；可导出JSON Schema。**退出条件：** 全节证据一致性验证、降级审计通过。不是生产纯确定性版本的强制前置。

## 14. P10：下游协议与生产只读运维

**目标：** 在保持独立仓库边界下让DragonBoatAI消费结构化结果。

| Task | 工作 | 验收 |
|---|---|---|
| DF-100 | `futures.market_analysis.published`事件/兼容版本/consumer contract | 下游读取action和hard_gate，no_trade不会转为弱买卖 |
| DF-101 | 同事务outbox、at-least-once发布、consumer去重、失败重投 | 模拟DB成功而发布失败可恢复，重复事件不重复处理 |
| DF-102 | 只读分析服务认证、限流、日志脱敏和凭证最小权限 | 无execution依赖/密钥；外部访问未授权被拒绝 |
| DF-103 | 备份、恢复演练、SQLite单写者、WAL和持久性配置 | 受控恢复后校验记录数及hash；不能只拷贝活动DB主文件宣称完整备份 |
| DF-104 | 可观测性：source延迟、batch失败、missing率、candidate率、LLM降级和锁等待 | 告警可复现，值班/恢复步骤明确 |
| DF-105 | 冻结artifact/config/schema并做小范围发布和回滚演练 | 保留旧读路径，数据追加不删除；迁移回滚不损失历史事实 |

输出：Agent契约、运行手册、部署配置、恢复报告、发布验收记录。若未来多机/多写者或写锁等待超出测定SLO，再评估PostgreSQL，不用数据库文件大小作为唯一迁移阈值。当前SQLite接口拒绝非SQLite URL，不能声称PostgreSQL已支持。

**退出条件：** G4，只读生产分析服务。自动下单仍需另外立项、账户权限、组合与独立风控验证，不由本计划授权。

## 15. P11：V2基本面与ML扩展

仅在数据质量和回放可信后进入，不与P0修复并行挤占范围。

| Task | 扩展 | 前置和验收 |
|---|---|---|
| DF-110 | Basis=可比现货-真实期货 | 品级/地点/税/币种/单位/发布时间可比，不能混用不匹配现货 |
| DF-111 | 库存/供需/季节性 | 以实际发布时点和历史修订入库，季节窗口只用当时已完成年份 |
| DF-112 | 品种profile及增量价值评估 | 新因子先shadow，校准和多重试验记录齐全 |
| DF-113 | 可选ML概率/区间预测 | 完整标签、时间隔离、样本外校准、漂移监测；未校准分数不叫概率 |

ML不取代规则风险硬门槛，不把历史最优模型永久作为当前最佳。新数据源授权/费用/保留政策必须先记录，不能静默引入付费依赖。

## 16. 测试矩阵与Definition of Done

| 类别 | 必须证明的性质 | 主要Task |
|---|---|---|
| 数学 | RSI/ATR/收益/归一化按冻结口径及边界准确 | DF-010/013/050 |
| PIT | bars/curve/spec/calendar/roll的未来修改不影响过去 | DF-022/033/041/070 |
| 合约 | 决策与生效分离、缺日不算连续、换月不制造收益 | DF-040至045 |
| 数据质量 | invalid/unknown不会变成安全候选 | DF-012/052/060 |
| 状态机 | cross、连续日、重复日、missing语义正确 | DF-062 |
| 幂等 | 请求/数据/核心版本身份可重复、并发安全 | DF-024/063/064 |
| 研究 | 样本外、标签结束时点、成本、消融透明 | DF-071至075 |
| 叙事 | 全节引用且含义一致、失败回退、不修改核心 | DF-090至093 |
| 运行 | 采集延迟、备份恢复、认证与告警有效 | DF-080至084/102至105 |

每阶段DoD：实现+测试+设计变更+迁移/回滚说明+实际运行证据；所有P0关闭；无私有数据进入仓库；代码审核通过；尚未执行的测试标NOT RUN。总覆盖率只作参考，不替代上述语义测试，也不机械追求通过增加简单测试提高比例。

## 17. 当前应交给Codex的一轮工作

仅执行PR-01和PR-02，不提前接数据源或ML。

```text
仓库：Amitfree-git/DragonFuture
先读 docs/DESIGN.md、docs/BASELINE_AUDIT.md、docs/IMPLEMENTATION_PLAN.md。
核对当前HEAD，不重置用户已有修改。
从main新建 feat/core-correctness-baseline（同名存在则先检查，不覆盖）。
复现原23项测试；记录环境和commit。
为AUD-01/05/08写失败回归样例，再进行DF-010至DF-014修正。
涉及PIT数据库和主力状态机的后续任务不要在本PR顺手重写。
更新特征/评分版本、变化说明和Golden期望；保留原版本记录。
运行新增及原有测试、compile、隔离迁移smoke。
提交小而可审查的PR，列出已做/未做、失败测试、兼容性及回滚方式。
未经数据门槛与研究验收，不把系统标为生产可用。
```

这里的分支和未来文件名是执行目标，不表示当前已创建PR或已修复缺陷。当前仍以本轮文档提交为终点。

## 18. 旧任务书映射与变更规则

旧`CODEX_TASK.md`的PR1-8保留作历史参考：旧PR1对应P00/P10；旧PR2-3对应P02/P03；旧PR4对应P04；旧PR5对应P02/P06；旧PR6对应P10；旧PR7对应P07；旧PR8对应P09。发生冲突以本主计划和DESIGN为准，不按旧任务书跳过正确性修正。

新增或关闭任务必须附PR/commit和证据，不把“文件已存在”直接标ACCEPTED。调整算法、单位、窗口、source policy、时间模式、main映射或风控阈值须更新设计、模型/配置版本及回放；文档纠错本身不强行升级业务schema。未决供应商、账户资格和历史vintage在对应阶段登记BLOCKED，不影响无关任务继续。
