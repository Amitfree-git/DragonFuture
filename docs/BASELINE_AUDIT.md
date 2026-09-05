# DragonFuture 0.1.0 基线审计与待办

日期：2026-09-05｜状态：已核查，缺陷尚未在本轮修复

基线commit：`e4fe4401281ee7ad069e5996a4cebf7e51dcaaa2`。
基线tree：`317b0c6ecd3fe9fcb3692d785961c6abdec8578a`。

本地会话备份DragonFuture.zip展开后，83个跟踪文件生成的Git tree与远端完全一致。因此本次代码检查及测试对应同一版本，不是用较旧ZIP推断当前main。此次只修改Markdown文档；下面的测试复现和静态检查不等于完整代码安全审计。

## 1. 本次实测与未执行项

在基线目录运行 `pytest -q`，23项通过。环境中Pydantic 2.13.4、SQLAlchemy 2.0.50、FastAPI 0.128.2、Alembic 1.18.4、pytest 9.0.2；Python版本及更多构建信息应在未来CI锁定并记录。

本次未重新测覆盖率、未重新进行全套迁移升降级、未跑真实数据回放、未接外部行情，也未验证交易盈利。原`VALIDATION_REPORT.md`中的83%覆盖率属于旧交付记录，不能归为本次测量。GitHub导入工作流成功只证明导入步骤完成。

## 2. 已复现的数值反例

现有RSI分别对上涨日列表和下跌日列表求均值，忽略各自在完整窗口中的出现次数：

```python
from dragonboat_ai.futures_agent.features.statistics import rsi
prices = [100.0]
for _ in range(13):
    prices.append(prices[-1] + 1)
prices.append(prices[-1] - 1)
print(rsi(prices, 14))  # 基线实际输出50.0
```

完整14个变化的初始平均涨幅为13/14、平均跌幅为1/14，RSI应为 `100-100/(1+13)=92.85714285714286`。本次单独执行已复现基线50.0；原23项测试仍通过，说明测试集合未覆盖此错误，而不是算法已正确。

## 3. 问题登记

P0=进入真实候选分析前必须解决；P1=相应功能发布前必须解决。以下链接指向实际源码，未来代码修复后应以基线commit查看旧行为。任务详见 [实施计划](IMPLEMENTATION_PLAN.md)。

| ID | 证据与当前行为 | 影响/目标 | 级别与任务 |
|---|---|---|---|
| AUD-01 | [statistics.py](../src/dragonboat_ai/futures_agent/features/statistics.py) 的rsi分别对非零涨/跌列表求均值；数值反例见上 | 改为明确Wilder口径、初始化和预热；更新特征版本 | P0；DF-010/014 |
| AUD-02 | [continuous_series.py](../src/dragonboat_ai/futures_agent/contracts/continuous_series.py) 加法后复权；[engine.py](../src/dragonboat_ai/futures_agent/features/engine.py) 对adjusted_settlement求比率收益；[repository](../src/dragonboat_ai/futures_agent/infrastructure/database/repositories.py)连续序列读取未按构建快照选版本 | 加法平移会改变百分比收益；需图区/收益分离和immutable series snapshot，不是只增加available_at就充分 | P0；DF-043/044/051 |
| AUD-03 | [main_contract_policy.py](../src/dragonboat_ai/futures_agent/contracts/main_contract_policy.py) 跳过无合格候选的历史日；[context_builder.py](../src/dragonboat_ai/futures_agent/application/context_builder.py)直接从近期曲线选合约，没有读取next-session生效映射 | 不能据此声称已保证连续完整交易日确认或下一交易日生效；需incumbent状态和effective_session | P0；DF-040至042 |
| AUD-04 | [ORM](../src/dragonboat_ai/futures_agent/infrastructure/database/models.py)合约规格无publication/received时间；[context_builder](../src/dragonboat_ai/futures_agent/application/context_builder.py) input hash未完整覆盖元数据/日历/roll信息，DTE用请求自然日期 | 元数据修订可能污染历史或缓存；需PIT规格、UTC与市场日期分离、完整manifest | P0；DF-022至025/063 |
| AUD-05 | [engine.py](../src/dragonboat_ai/futures_agent/features/engine.py)限价判断用严格大于/小于，触及边界不纳入0距离；[opportunity](../src/dragonboat_ai/futures_agent/scoring/opportunity_engine.py)缺失流动性默认50；[risk](../src/dragonboat_ai/futures_agent/scoring/risk_engine.py)部分读取不查metric.status | 边界或未知可能被低估；关键输入missing/invalid须block；触及等于最高接近风险，越界隔离 | P0；DF-011/012/060 |
| AUD-06 | [invalidation/engine.py](../src/dragonboat_ai/futures_agent/invalidation/engine.py)单点evaluate把cross_below当lt，未使用连续日历史计数 | “连续两日/发生跨越”文字尚无对应状态机保障；需历史、streak、幂等和unknown | P0（失效功能）；DF-062 |
| AUD-07 | [engine.py](../src/dragonboat_ai/futures_agent/features/engine.py)多组指标共用连续/合约数据的最大available_at；[data_quality.py](../src/dragonboat_ai/futures_agent/scoring/data_quality.py)也主要看最大时间 | 陈旧依赖可被新鲜另一来源掩盖；需按依赖链和交易日周期评估freshness | P0；DF-024/052/061 |
| AUD-08 | [engine.py](../src/dragonboat_ai/futures_agent/features/engine.py) volume_zscore_20d使用volumes[-61:-1]；部分样本质量用总价格数；extension混用连续相对MA距离和真实合约ATR比例 | 名称/窗口/样本数及ATR量纲不一致；需登记真实公式、统一来源和预热 | P0；DF-013/045/050 |
| AUD-09 | [engine.py](../src/dragonboat_ai/futures_agent/features/engine.py)曲线取最近两个正DTE点；[regime](../src/dragonboat_ai/futures_agent/regime/classifier.py)用综合Curve Score判结构，change缺失也可能标strengthening | 需合格/可比期限、原始斜率定事实、unknown变化，不把合约对切换当信号 | P0；DF-034/053 |
| AUD-10 | [analyst.py](../src/dragonboat_ai/futures_agent/application/analyst.py)质量检查后仍继续评分；叙事生成后才统一保存核心；[models](../src/dragonboat_ai/futures_agent/domain/models.py)没有全部跨字段约束 | 数据阻断不等于正常方向；叙事失败回退虽存在，长超时仍延后核心保存；需先保存与联动约束 | P0；DF-012/060/064 |
| AUD-11 | [llm_adapter.py](../src/dragonboat_ai/futures_agent/narrative/llm_adapter.py)只对bullish_case/bearish_case验证引用存在；[models](../src/dragonboat_ai/futures_agent/domain/models.py) extra/frozen未开启全面strict，嵌套list仍可改 | ID有效不证明句子受支持；需全节数字/含义校验、严格输入与深层不可变策略。实际类名是LLMNarrativeGenerator | P1；DF-060/091至093 |
| AUD-12 | [analyst.py](../src/dragonboat_ai/futures_agent/application/analyst.py)request hash含include_narrative，版本含prompt；[routes](../src/dragonboat_ai/futures_agent/api/routes.py)latest缺exchange/contract/as_of过滤；[session](../src/dragonboat_ai/futures_agent/infrastructure/database/session.py)仅支持SQLite | 叙事/核心身份应拆分，latest不可穿越未来或跨交易所；PostgreSQL支持尚不存在 | P1；DF-063/065/105 |

## 4. 已有实现不应被重复重写

已有可保留的模块包括：领域分数与时区校验；日行情/曲线可见修订查询；Feature/Factor及分析落库；方向有效权重门槛；风险硬门槛框架；模板回退；缓存的请求/输入/版本联合约束。目标是在这些边界内修正语义和补测试，不把“存在缺陷”解读成要抛弃整个工程。

## 5. 文档与演示中的解释限制

`confidence=99.917...` 是合成数据上的启发式证据评分，不是99.9%预测正确率。`wait_for_pullback` 是研究动作，不是下单。加法后复权不自动保证任何指标都无换月偏差。禁止发布“无未来函数”绝对结论，直到bars、元数据、修订、日历、移仓及标签全链路测试完成。

旧`CODEX_TASK.md`出现22项测试、`StructuredLLMNarrativeGenerator`等与当前实现不一致的历史表述；新任务以实施主计划和实际类/命令为准。旧报告的GitHub无法访问说明也是历史状态，不是当前授权状态。

## 6. 关闭规则

审计项关闭需要：修复PR/commit、失败到通过的回归样例、影响的配置/特征/schema版本、Golden变化理由及实际运行日志。不能仅凭修改说明或Prompt承诺关闭。每轮执行前核对HEAD；本表是固定基线审计，不自动反映未来分支状态。
