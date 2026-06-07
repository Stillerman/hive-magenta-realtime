#!/usr/bin/env bash
# Start the Hive server. Open http://localhost:8000 on the projector.
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python -m server --port "${PORT:-8000}" "$@"
