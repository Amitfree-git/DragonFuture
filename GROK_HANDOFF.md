# DragonFuture — Grok Bot 本机分析请求与查询入口

用户已要求修复 DragonFuture 并交给 Grok Bot 使用，并明确授权向 Grok 披露调用路径和研究结果、让 Grok 发出分析请求。服务运行在用户这台 Mac；不是 Grok 的云端电脑。请使用内置 Shell/Read 的明确本机 machineId。不要省略 machineId，也不要把 Mac 路径注册成云端 stdio MCP。

## 默认工作流：先更新日线再分析

用户现在要求分析请求能更新行情。后续需要最新结构分析时，优先在当前Mac的明确machineId上运行：

```sh
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py refresh_and_analyze --symbol RB --exchange SHFE --horizon swing
```

中周期将`--horizon swing`改为`--horizon position`。命令调用`POST /api/v1/futures/refresh_and_analyze`，JSON只接受symbol、exchange、horizon；不接受历史as_of、路径、令牌或数据源地址。历史复核继续使用下面的普通分析POST。

本机启动入口 scripts/serve_corrected.sh 默认使用 wind-tushare-MCP：DragonFuture 通过本机 stdio MCP 获取 Tushare 原始数据，再检查交易所日历与已发布日线、回查近期修订、验证覆盖、重建主力与研究序列并分析。成功响应 refresh.source=wind_tushare_mcp，附 mcp_request_ids；请以本次响应为实际来源依据。不要读取、打印或发送令牌。

返回`refresh`和`analysis`：必须披露refresh目标日/实际数据日/更新状态，并原样保留analysis的action、hard_gate和data_mode。`up_to_date`表示已向供应商核验过且无新增或修订，不表示本分钟有行情。数据仍是final_only；缺失涨跌停等关键字段仍阻断，不能补造。供应商、日历、数据完整性或重建失败时报告refresh_failed，不静默回退latest冒充已更新。

单次可能等待数十秒；客户端最多等待180秒。若超时，先查看服务状态，避免连续重复触发；协调器会阻止并行刷新。此入口不采盘中行情、不下单、不新增定时任务。

## 先核验服务与覆盖范围

```sh
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py status
```

## 主动发起分析请求

`POST /api/v1/futures/analyses` 接收品种、交易所、周期和带时区的截止时间，执行确定性分析并保存研究结果；它不会采集新行情或下单。已有相同请求及版本的结果可能复用缓存。`latest` 只查询已有结果，不能代替发起分析。

先用 status 查看覆盖范围。当前已验收 RB / SHFE 和 M / DCE，数据截至日期以响应为准。周期为 swing（短周期）或 position（中周期），不能把固定示例日期当作永久最新。截止时间必须带时区；真实最新数据日期与请求截止时间分别披露。

本次接入验收在本机 Shell 执行以下请求，使用固定截止时间方便核对（16:01不意味着存在该分钟的行情）：

```sh
curl --silent --show-error --fail-with-body --max-time 30 \
  -X POST http://127.0.0.1:8000/api/v1/futures/analyses \
  -H 'Content-Type: application/json' \
  --data '{"symbol":"RB","exchange":"SHFE","horizon":"swing","as_of":"2026-09-04T16:01:00+08:00","include_narrative":false,"force_refresh":false}'
```

API不直接连接订单系统；此POST只写入分析、特征和审计状态。禁止改数据库或配置以绕过风险门槛。服务报错就报告错误；不要启动旧服务绕过。若未来启用API鉴权，通过既有本机凭据机制传递，不能把令牌贴到聊天里。

拿到 analysis_id 后，可 GET `/api/v1/futures/analyses/{analysis_id}` 复核持久化。核验 `versions.code_commit` 与 status 的 `code_artifact` 一致。随后运行下方 latest 脚本，它会验证版本、新鲜度并保留风险阻断。

## 查询 RB 最新结构化研究结果

```sh
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py latest --symbol RB --exchange SHFE
```

其他品种必须先确认 status 中存在。指定历史截止时刻用 `--as-of 2026-09-04T16:00:00+08:00`，持仓周期用 `--horizon position`；未生成相应结果返回 unavailable，禁止编造。

## 查看原判断的失效跟踪

```sh
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py invalidation --analysis-id <上一步的analysis_id>
```

失效状态按后续分析实际观测的交易日更新；没有新分析时不会自动追踪。不能将旧状态解释为实时监控结论。

## 解释规则

- 这是独立的确定性市场分析服务，不是订单接口；查询命令使用GET，refresh_and_analyze使用固定更新分析POST，普通历史分析使用下方POST。
- 原样读取 direction、opportunity.action、risk.hard_gate_triggered、data_quality、data_mode、版本与as_of。
- `no_trade` / `insufficient_data` / hard_gate=true 必须解释为阻断，不可降格为“弱买入/弱卖出”。方向分不是买卖指令，confidence不是胜率。
- 当前数据是Tushare来源的final_only历史日线，已验收的品种为RB和M；最新数据日期以status响应为准，不是实时行情，也没有严格历史vintage认证。
- production_ready=false 是明确边界。可用于研究解释和故障诊断，不用于自动下单、修改持仓或放松风控。
- 使用status中的code_artifact核验分析版本；脚本发现不匹配、过期或服务错误会阻断，不可改查原来的旧数据库来绕过。
- 盘中实时行情仍使用已有Wind/Tushare能力；供应商的实时主力映射与DragonFuture按观测日确认的研究主力映射可能不同，分别注明口径。

请先运行 status，再实际 POST 生成分析，按返回analysis_id读取确认，并运行 latest；把HTTP状态、analysis_id、数据模式、请求截止时间、实际最新数据日期、选定合约、action、hard_gate、code_artifact及core_result_hash报告给用户，完成接入验收。保存该调用入口供后续按用户请求主动分析使用。后续期货研究需要确定性结构分析时，可重复调用这个入口。


## 2026-09-06 豆粕与部分历史字段修复

M / DCE 已成功刷新和分析，不应再根据旧 status 断言只支持 RB。status 显示已入库可用范围，不是产品支持白名单。其他品种仍须分别刷新验收。

豆粕请求：
```sh
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py refresh_and_analyze --symbol M --exchange DCE --horizon swing
/Users/amitfree/Documents/dragonfuture/.venv/bin/python -B /Users/amitfree/Documents/dragonfuture/scripts/grok_query.py refresh_and_analyze --symbol M --exchange DCE --horizon position
```

refresh.bars_partial_ohlc 为本次采集窗口部分 OHLC 缺失记录数，不是丢弃数。结算价/成交量/持仓完整的记录保留，缺失价格不填造。研究连续指数使用同合约结算收益；主力切换规则没有改变。当前所选合约 ATR 窗口缺高低价时，指标不可用，入场门槛 missing_entry_atr 阻断。结算价、成交量、持仓或交易日缺失仍按完整性要求失败。

此次豆粕初始补采保留21条部分OHLC记录（含原先8条有成交记录）；后续增量窗口返回0不表示历史21条已修复。行情仍为已发布日线，实际日期以响应为准。unknown_price_limit_risk 仍可能导致 no_trade，不能把可分析解释为可交易。


## 2026-09-06 ft_limit 已补接（优先于前述缺涨跌停的历史验收结论）

refresh_and_analyze 现在按实际合约和交易日采集 Tushare ft_limit，归档原始响应、追加修订并重新计算风险。bars_with_price_limits / bars_missing_price_limits 描述本次刷新窗口的完整与缺失数量。缺失、无效或接近涨跌停仍按既有门槛处理；禁止把之前的 unknown_price_limit_risk 当成永久状态。必须读取本次实际结果，no_trade 可能解除，但不代表允许自动下单。

2026-09-06 已实现 MCP 原始数据适配，启动入口默认选择 MCP。RB/M 跨换月原始数据和隔离刷新输入哈希、风控结果双路对账一致。仍保持盘后 final_only、production_ready=false；MCP 接入不改变研究用途边界。显式回退需设置 DRAGONBOAT_FUTURES_SOURCE=tushare_http 并重启。

限价与日线按日期匹配，不用次日价格带解释前一交易日，不用于当前盘中可交易性判断。本次默认回查最近10个自然日，未自动回填全部历史限价。初次历史导入若带限价，合并日线最早可见时间为本次接收时间；不宣称严格历史数据版本已还原。

## 2026-09-09：港美股日线与供应商换月查询

新增独立只读 API，不向期货数据库写入港美股数据，也不调用期货评分器：

- `POST http://127.0.0.1:8000/api/v1/market-data/price_history`
  - 港股：`{"asset_type":"hk_stock","code":"00700.HK","start":"20260901","end":"20260904"}`
  - 美股：`{"asset_type":"us_stock","code":"AAPL","start":"20260901","end":"20260904"}`
- `POST http://127.0.0.1:8000/api/v1/market-data/futures_main_mapping_history`
  - `{"product":"RB","exchange":"SHFE","start":"20260901","end":"20260904","mode":"strict"}`
- `POST http://127.0.0.1:8000/api/v1/market-data/futures_roll_events`
  - `{"product":"RB","exchange":"SHFE","start":"20260901","end":"20260904","price_field":"settle"}`

所有路径沿用现有本机连接方式与鉴权。日期可用 YYYYMMDD 或 YYYY-MM-DD；这里 start/end 指市场当地交易日期范围，不是历史可得时间 as_of。

先检查 HTTP 状态和 ok，再检查 data.complete/completeness、缺口与 warnings。映射/换月可能成功返回不完整材料，不等于可计算或可交易。该映射是供应商口径，不替代 DragonFuture 的自定义主力规则。

港美股实际来源目前为 Yahoo，经 wind-tushare-MCP 获取；不是 Wind 港美股行情。00700.HK 归一为0700.HK，保留 source、currency、market_timezone、request_id。close 与 yahoo_adj_close 分开；后者不等于 qfq/hfq，只允许 adjust=none，不允许自行把供应商复权价改名为前复权价。complete 表示供应商响应采集状态，不证明覆盖全部应有交易日。缺失字段保持 null，禁止补造。

这些入口返回研究原始数据，没有 DragonFuture 港美股方向/机会/风险评分，也没有期货 analysis_id。不得把空记录、限流或 provider 禁用解释为“行情没有波动”。期货 refresh_and_analyze 地址和默认来源保持现状。
