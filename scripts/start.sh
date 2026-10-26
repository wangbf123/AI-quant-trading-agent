#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${AQR_VENV:-$project_dir/.venv}"
cd "$project_dir"
if [[ ! -f frontend-v2/dist/index.html ]]; then
  npm run build --prefix frontend-v2
fi
exec "$venv_dir/bin/python" frontend-v2/backend/app.py
