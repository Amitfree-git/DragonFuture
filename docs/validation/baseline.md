# 基线复现记录（P00 / DF-000–DF-003）

记录日期：2026-09-05  
基线 commit：`cc899bd491f9f43f7c0f67517229fc0c2460e392`  
代码身份仍对应审计中的 `e4fe440` 源码树；`cc899bd` 只增加设计文档。

## 环境

```text
OS: macOS darwin 25.6.0
Python: 3.13.12
pydantic: 2.13.5
SQLAlchemy: 2.0.52
FastAPI: 0.141.1
Alembic: 1.19.2
pytest: 9.1.1
```

依赖锁定见仓库根目录 `requirements.lock`（`pip freeze --exclude-editable`）。本地开发包仍以 `pyproject.toml` 的范围约束为准；CI 先装 lock，再 `pip install --no-deps -e .`，避免范围约束把已锁定版本再解析上去。

## 命令与结果

| 命令 | 退出码 | 结果 |
|---|---:|---|
| `pytest -q` | 0 | 23 passed |
| `python -m compileall -q src tests examples scripts alembic` | 0 | 通过 |
| 隔离 SQLite 上 `alembic upgrade head && check && downgrade base && upgrade head` | 0 | 见本轮 CI / 本地 smoke |

`examples/demo_analysis.json` 仍是合成数据演示，不是真实行情验收。`VALIDATION_REPORT.md` 是历史交付记录，不代表本轮测量。

## 审计账本

AUD-01 至 AUD-12 已在 [BASELINE_AUDIT.md](../BASELINE_AUDIT.md) 建账。本文件只证明基线可复现；缺陷关闭以修复 PR 和失败→通过的回归测试为准。
