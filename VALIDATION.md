# 本地验证记录

验证日期：2026-09-04

## 执行环境

```text
OS: Linux x86_64
Python: 3.13.5
```

本次运行环境中已安装的主要依赖版本由实际测试环境提供；项目本身在 `pyproject.toml` 中声明支持 Python 3.11 及以上，并由 GitHub Actions 配置 Python 3.11、3.12、3.13 测试矩阵。

## 已执行验证

### 1. 全量测试

```bash
PYTHONPATH=src pytest -q
```

结果：

```text
22 passed
```

覆盖：

- 标准化函数；
- 请求代码规范化与配置强校验；
- 缺失因子权重；
- 持仓证据类型；
- 主力合约确认、交替挑战者和最低流动性份额；
- point-in-time 修订可见性；
- SQLAlchemy 行情读取；
- 风险硬门槛；
- `wait_for_pullback`；
- 分析缓存与 `force_refresh` 审计；
- FastAPI；
- Alembic；
- SQLAlchemy 完整结果往返；
- RB Golden Test。

### 2. Python 字节码编译

```bash
python -m compileall -q src tests examples scripts alembic
```

结果：通过。

### 3. Wheel 构建

```bash
python -m pip wheel . --no-deps --no-build-isolation -w dist
```

结果：成功生成：

```text
dist/dragonboat_futures_agent-1.0.0-py3-none-any.whl
```

### 4. Wheel 独立目录安装

```bash
python -m pip install \
  --target /tmp/futures_agent_wheel_install \
  --no-deps \
  dist/dragonboat_futures_agent-1.0.0-py3-none-any.whl
```

验证包内默认 YAML 可以读取，演示分析可以运行。

### 5. 安装态 CLI

```bash
futures-agent-demo --horizon swing --no-narrative
```

结果摘要：

```text
selected_contract: RB2701
direction: bullish
opportunity: wait_for_pullback
metrics: 34
factors: 4
```

### 6. Alembic 往返

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

结果：通过。最终创建 20 张业务表及 `alembic_version`。

### 7. SQLite 分析持久化

```bash
python scripts/seed_demo_db.py \
  --database-url sqlite:////tmp/futures_agent_seed.sqlite
```

实际写入：

```text
fut_analysis_run: 1
fut_feature_value: 34
fut_factor_snapshot: 4
fut_analysis_evidence: 4
fut_invalidation_rule: 3
```

## 未在当前容器执行的检查

当前容器最初未安装 Ruff 和 mypy，且普通 pip 隔离构建无法联网下载构建依赖。因此本地验证以测试、`compileall`、Wheel 构建、安装态运行和迁移往返为主。

仓库已配置 CI 在安装开发依赖后执行：

```bash
ruff check src tests
pytest -q
alembic upgrade head
```

合入 DragonBoatAI 前，应以项目正式 CI 的 Ruff 结果作为静态检查门槛；如启用严格 mypy，还需在主项目类型约定下单独处理。
