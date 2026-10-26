#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${AQR_VENV:-$project_dir/.venv}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$project_dir/.cache/pip}"
export npm_config_cache="${npm_config_cache:-$project_dir/.cache/npm}"
python3 -m venv "$venv_dir"
# Install the official CPU wheel first; avoid pulling an unused CUDA stack.
"$venv_dir/bin/python" -m pip install --disable-pip-version-check 'torch==2.6.0+cpu' --index-url https://download.pytorch.org/whl/cpu
"$venv_dir/bin/python" -m pip install --disable-pip-version-check -r "$project_dir/requirements/research.lock"
SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0 "$venv_dir/bin/python" -m pip install --no-deps -e "$project_dir"
"$venv_dir/bin/python" -m pip check
npm ci --prefix "$project_dir/frontend-v2" --no-audit --no-fund
npm run build --prefix "$project_dir/frontend-v2"
printf 'Environment prepared. Interpreter: %s/bin/python\n' "$venv_dir"
