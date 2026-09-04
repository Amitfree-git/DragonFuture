# 期货行情分析 Agent V1 — 验证报告

验证日期：2026-09-04  
交付版本：`0.1.0`

## 1. 验证环境

| 组件 | 版本 |
|---|---:|
| Python | 3.13.5 |
| Pydantic | 2.13.4 |
| SQLAlchemy | 2.0.50 |
| FastAPI | 0.128.2 |
| Alembic | 1.18.4 |
| PyYAML | 6.0.3 |
| pytest | 9.0.2 |
| pytest-cov | 7.0.0 |

项目声明的运行和开发依赖均已逐项检查，当前安装版本全部落在 `pyproject.toml` 规定的范围内。

## 2. 测试结果

```text
23 passed
总覆盖率：83%（包含分支覆盖）
```

测试覆盖以下关键行为：

- 严格领域模型和时区校验；
- Robust Z-score、分位数及边界映射；
- 缺失因子不转换为零分；
- 方向因子有效权重门槛；
- 主力合约连续确认与到期排除；
- 后向加法连续合约消除移仓跳空；
- 高风险硬门槛覆盖高方向分；
- 价格过度延伸时输出 `wait_for_pullback`；
- 日行情修订的 point-in-time 可见性；
- 请求、输入数据和完整模型版本的缓存隔离；
- 评分配置内容哈希参与缓存身份；
- Feature Snapshot 和 Factor Snapshot 实际落库；
- LLM 多空论据缺少或伪造 `evidence_id` 时被拒绝并回退；
- FastAPI 健康检查、创建分析、按 ID 读取、最新结果和 404 路径。

## 3. 数据库迁移验证

执行序列：

```bash
alembic upgrade head
alembic check
alembic downgrade base
alembic upgrade head
alembic check
```

结果：

```text
业务表：20
升级成功：是
降级至 base：是
再次升级：是
Alembic metadata 差异：无
```

`fut_analysis_run` 已包含：

```text
version_hash
data_version
score_config_hash
```

`fut_factor_snapshot` 已按以下字段区分因子快照：

```text
factor_model_version
score_config_version
score_config_hash
```

## 4. 端到端演示

模拟数据：螺纹钢 `RB`，分析时间为 `2026-09-04T17:00:00+08:00`。

```text
selected_contract       RB2701
primary_regime          strong_bull_trend
direction               strong_bullish
direction_score         76.96622666676399
opportunity             wait_for_pullback
opportunity_score       56.576195679366975
confidence              99.91745898935598
risk                    28.043228222086288
metrics                 29
evidence                13
invalidation_conditions 3
```

数据库落库结果：

```text
feature_snapshot_rows  1
feature_value_rows     29
factor_snapshot_rows   4
```

在两次完全重建演示数据库后重复运行，`analysis_id` 会变化，但确定性核心哈希保持一致：

```text
core_result_hash = 37bcdbca706f29515a51aadbdf5b8b4c16134b98d8933adbadecca1a70c854f1
```

所有模板叙事中的多头和空头论据均携带有效 `evidence_id`。

## 5. 构建验证

```text
compileall：通过
editable install：通过
wheel build：通过
```

生成的 Wheel：

```text
dragonboat_futures_agent_v1-0.1.0-py3-none-any.whl
SHA-256: 384f9e94758c98db861a324a298b459525784ab9e901810fef690c90a371a89a
```

## 6. 非阻断环境说明

当前共享构建容器的全局 Python 环境存在一项与本项目无关的 `moviepy` / `Pillow` 版本冲突。该依赖不在本项目的依赖树中，不影响本项目的导入、23 项测试、数据库迁移、演示运行或 Wheel 构建。项目自身声明的依赖范围检查全部通过。

## 7. 尚未执行的外部集成

本次未直接写入 DragonBoatAI 的正式 GitHub 仓库：已连接的 GitHub 账户没有返回任何可访问仓库。因此交付物采用独立可运行项目和 drop-in 源码结构。合并步骤与不可破坏的工程约束见 `CODEX_HANDOFF.md`。
