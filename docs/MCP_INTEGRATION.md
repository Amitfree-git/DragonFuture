# DragonFuture MCP 数据源

DragonFuture 支持 `DRAGONBOAT_FUTURES_SOURCE=mcp`，通过本机 stdio MCP 获取合约资料、显式实际合约日线、涨跌停和交易日历。MCP 上游仍为 Tushare；主力规则、研究收益、风险和失效条件由 DragonFuture 计算。

## 配置

```sh
export DRAGONBOAT_FUTURES_SOURCE=mcp
export DRAGONBOAT_FUTURES_MCP_COMMAND='["/Users/amitfree/.local/bin/node","/Users/amitfree/mcp-servers/wind-tushare-mcp/src/index.mjs"]'
export DRAGONBOAT_FUTURES_MCP_TIMEOUT=45
```

命令是 JSON 参数数组，不通过 shell 执行。服务器继承运行环境中的上游凭据，DragonFuture 不在响应中输出凭据。每次 refresh 创建独立 MCP 会话，先初始化/发现能力/读取 data_source_guide，结束、失败、超时均关闭进程组。这里的超时是每次工具调用上限，不是整个历史刷新总耗时。

通用应用未配置时默认仍为 `tushare_http`，本机 `scripts/serve_corrected.sh` 启动入口默认选择 MCP；未知来源配置直接失败，不静默回退。回退时显式设置 `DRAGONBOAT_FUTURES_SOURCE=tushare_http` 并重启服务。

## Grok 调用保持不变

`POST http://127.0.0.1:8000/api/v1/futures/refresh_and_analyze`

例如：`{"symbol":"M","exchange":"DCE","horizon":"swing"}`。

先判断 HTTP/业务是否成功。成功响应 `refresh.source=wind_tushare_mcp` 表示本次实际使用 MCP；`mcp_request_count` 和 `mcp_request_ids` 用于查询链追踪。普通只读分析接口不会自动更新行情。

数据来源错误返回已有的阻断响应，不使用旧分析伪装刷新成功。MCP 缺失价格带保留 null，继续由既有风控拒绝不可交易数据；结构错误、截断、非法价格带不得当作完整结果。

## 数值与可追溯性

MCP 的 JavaScript JSON 序列化会把浮点整数去掉 `.0`。适配器按 Tushare 的日线与价格带字段类型恢复 float，避免运输格式差异造成伪修订；缺失值不补零。价格带仅保留原始四字段参与既有哈希，网关注释另行记录。

MCP request_id、schema/server version、接收时间、查询参数、供应商与输入哈希归档到数据库旁 `raw_archive`，在批次提交前写入归档索引。供应商仍标注 tushare，传输路径通过批次 source_policy=tushare_via_mcp 区分。商业数据归档与数据库不得提交 Git。

## 限定

- 日线和历史映射保持 final_only，不能冒充历史时间点可得数据。
- 不用供应商主力序列替代 DragonFuture 自定义切换路径。
- 原始日线和价格带按每合约至多366自然日分窗；任一分窗异常，不返回部分合并数据。
- 暂不提供远程 HTTP MCP；仅支持本机 stdio 服务。
- 不自动切换至 Wind 或其它上游；未来新增供应商需另行校验字段和数据语义。

## 港美股及换月原始查询（2026-09-09）

新增 `/api/v1/market-data/price_history`（POST，asset_type=hk_stock/us_stock，code/start/end）、`futures_main_mapping_history`（product/exchange/start/end/mode）、`futures_roll_events`（product/exchange/start/end/price_field）。这些相对路径均在 `/api/v1/market-data/` 下。

实现类为 `McpMarketQueries`，与 `McpFuturesSource` 的入库功能分离，复用相同会话与命令配置。港美股来源Yahoo，保留供应商复权口径、货币与当地时区，不接期货评分。缺口标记和查询追踪完整返回；不返回期货analysis_id。

公共HTTP入口仅白名单化这三种操作，禁止透传任意MCP工具或执行命令。单次日期跨度至多3660自然日。沿用API令牌与限速，中途异常/成功均关闭MCP会话。详细请求示例见 GROK_HANDOFF.md。
