#!/usr/bin/env bash
# Install everything Hive needs: Python venv + deps, the UI, and the model.
set -euo pipefail
cd "$(dirname "$0")"

command -v uv  >/dev/null || { echo "Install uv: https://docs.astral.sh/uv/"; exit 1; }
command -v npm >/dev/null || { echo "Install Node.js (provides npm): https://nodejs.org"; exit 1; }
command -v cloudflared >/dev/null || brew install cloudflared

uv venv --python 3.12
uv pip install -r requirements.txt
npm --prefix ui install
npm --prefix ui run build
.venv/bin/mrt models init
.venv/bin/mrt models download mrt2_small

echo "Done. Start Hive with: ./run.sh"
