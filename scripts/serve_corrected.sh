#!/bin/sh
set -eu
cd /Users/amitfree/Documents/dragonfuture
export DRAGONBOAT_FUTURES_DATABASE_URL=sqlite:////Users/amitfree/Documents/dragonfuture/data/futures_corrected.db
export DRAGONBOAT_FUTURES_CONFIG=/Users/amitfree/Documents/dragonfuture/config/futures_v1.yaml
export PYTHONDONTWRITEBYTECODE=1
export DRAGONBOAT_FUTURES_SOURCE="${DRAGONBOAT_FUTURES_SOURCE:-mcp}"
if [ -z "${DRAGONBOAT_FUTURES_MCP_COMMAND:-}" ]; then
    export DRAGONBOAT_FUTURES_MCP_COMMAND='["/Users/amitfree/.local/bin/node","/Users/amitfree/mcp-servers/wind-tushare-mcp/src/index.mjs"]'
fi
export DRAGONBOAT_FUTURES_MCP_TIMEOUT="${DRAGONBOAT_FUTURES_MCP_TIMEOUT:-45}"
exec /Users/amitfree/Documents/dragonfuture/.venv/bin/python -m uvicorn dragonboat_ai.futures_agent.api.app:create_app --factory --host 127.0.0.1 --port "${DRAGONFUTURE_PORT:-8000}"
