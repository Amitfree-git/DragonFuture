# DragonFuture：期货行情分析 Agent V1

> **详细设计与实施主计划（2026-09-05）：** 请先阅读[系统详细设计](docs/DESIGN.md)、[实施主计划](docs/IMPLEMENTATION_PLAN.md)及[基线审计](docs/BASELINE_AUDIT.md)。当前0.1.0仍是存在已登记正确性缺口的参考实现；合成测试通过不代表生产或交易有效性验收。本次仅补齐文档，不修改业务实现。

DragonFuture 是一个独立的日频期货行情分析工程，同时保留 `dragonboat_ai.futures_agent` 包路径，便于未来合并到 DragonBoatAI。它以确定性计算为核心，重点保证 **point-in-time 数据安全、真实合约与连续合约隔离、结果可回放、证据可审计**。

## V1 已实现

- 趋势、动量、价格—持仓结构、期限结构四类方向因子；
- 波动率、流动性、到期/移仓和涨跌停接近度等环境与风险指标；
- `Market Regime / Direction / Opportunity / Confidence / Risk / Invalidation` 六类核心输出；
- 严格的 Pydantic v2 领域模型；
- 20 张 SQLAlchemy 2.0 业务表及 Alembic 初始迁移；
- 使用 `available_at <= as_of` 的历史时点查询和可见修订选择；
- 主力合约连续确认策略和后向加法连续合约构造器；
- FastAPI 接口、模板化叙事、模拟螺纹钢数据和端到端测试。
- 提供商无关的结构化 LLM 叙事适配器；多空论据必须通过 `evidence_id` 校验。

V1 面向中低频日线分析，不使用 Tick、Level-2、秒级或分钟级数据；不负责实际下单、仓位分配和组合优化。

## 核心原则

1. 连续合约只服务于趋势、动量和波动率；持仓、流动性、到期风险与期限结构使用真实合约。
2. 数据日期和数据可获得时间分开保存，历史分析只能读取当时已经发布的数据。
3. 数据修订采用追加版本，不能覆盖历史信息集。
4. 缺失因子保持缺失，不能转换成“中性零分”。
5. 方向判断与当前入场机会分开计算。
6. 高方向分不能越过数据、流动性、到期、涨跌停等硬风险门槛。
7. LLM 或叙事层失败时，确定性核心 JSON 仍然可用。
8. 缓存要求请求、输入数据哈希和完整模型版本哈希全部一致。

## 安装与验证

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

执行数据库迁移：

```bash
alembic upgrade head
```

运行模拟行情分析：

```bash
python scripts/demo_analysis.py
```

命令会自动重建一次性演示数据库，并将完整结果写入：

```text
outputs/demo_analysis.json
```

仓库内还提供一份固定示例：

```text
examples/demo_analysis.json
```

启动 API：

```bash
uvicorn dragonboat_ai.futures_agent.api.app:create_app \
  --factory --host 127.0.0.1 --port 8000
```

可通过环境变量指定数据库和评分配置：

```bash
export DRAGONBOAT_FUTURES_DATABASE_URL='sqlite:///data/futures_agent.db'
export DRAGONBOAT_FUTURES_CONFIG='config/futures_v1.yaml'
```

## 合并到现有 DragonBoatAI

1. 将 `src/dragonboat_ai/futures_agent/` 复制到现有 `src/dragonboat_ai/`。
2. 合并 `pyproject.toml` 中的依赖，不能覆盖原项目配置。
3. 将 Alembic revision 复制到原迁移目录，并把 `down_revision` 改为原项目当前 head。
4. 复用现有数据库引擎和 Session Factory，适配两个 SQLAlchemy Repository。
5. 将 futures router 接入现有 FastAPI application factory。
6. 用真实日行情适配器替换 `infrastructure/demo_data.py`。
7. 保留 `available_at`、`revision_no`、来源合约、输入哈希和模型版本字段。
8. 同时运行原项目测试和本包测试，再创建 Pull Request。

详细执行要求见 [`CODEX_HANDOFF.md`](CODEX_HANDOFF.md)，验证结果见 [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md)。

## 生产数据适配器最低要求

生产适配器至少应提供：

- 品种及真实合约元数据；
- 真实合约 OHLC、结算价、成交量、持仓量和涨跌停价；
- 每条数据及每次修订的 `available_at`；
- 带来源合约血缘的后复权连续结算价；
- 同一时点至少两个流动合约组成的期限结构快照。

收盘价与结算价必须独立保存。下游策略、组合、CIO、风控和执行 Agent 应读取结构化字段，不能从自然语言报告反向解析评分。
