#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap for DragonFuture.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

# The stdlib venv builder needs ensurepip, which the base image may lack.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y --no-install-recommends python3-venv
fi

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -e '.[dev]'

# Apply the Alembic schema and seed the disposable synthetic demo database so
# the API terminal can serve analyses immediately.
mkdir -p data outputs
./.venv/bin/alembic upgrade head
./.venv/bin/python scripts/demo_analysis.py >/dev/null
