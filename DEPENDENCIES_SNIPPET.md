# 依赖合并片段

将以下运行依赖合并到现有 DragonBoatAI 的 `[project].dependencies`，不要覆盖原有条目：

```toml
"pydantic>=2.12,<3",
"SQLAlchemy>=2.0,<3",
"fastapi>=0.120,<1",
"uvicorn>=0.35,<1",
"PyYAML>=6,<7",
```

开发与测试依赖：

```toml
"alembic>=1.16,<2",
"httpx>=0.27,<1",
"pytest>=8,<10",
"pytest-cov>=5,<8",
```

若原项目已声明这些包，应按照原项目的兼容性矩阵合并版本范围，并运行完整回归测试。
