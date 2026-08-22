#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
venv_python="$script_dir/.venv/bin/python"
bootstrap_python=${INUYASHA_BOOTSTRAP_PYTHON:-python3}

if ! command -v "$bootstrap_python" >/dev/null 2>&1; then
  printf '%s\n' "Python 3 was not found: $bootstrap_python" >&2
  printf '%s\n' "Set INUYASHA_BOOTSTRAP_PYTHON for this command to a Python 3 executable." >&2
  exit 1
fi

"$bootstrap_python" -m venv "$script_dir/.venv"
PIP_NO_CACHE_DIR=1 "$venv_python" -m pip install --upgrade pip
PIP_NO_CACHE_DIR=1 "$venv_python" -m pip install -r "$script_dir/requirements-dev.txt"

printf '%s\n' "Project Python environment is ready: $venv_python"
printf '%s\n' "Only this repository's .venv was changed."
