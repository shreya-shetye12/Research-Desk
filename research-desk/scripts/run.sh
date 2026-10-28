#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ -n "${CONDA_PREFIX:-}" ]; then
    SHIFT_RUNTIME_PYTHON="$CONDA_PREFIX/bin/python"
elif [ -x .venv/bin/python ]; then
    SHIFT_RUNTIME_PYTHON=".venv/bin/python"
else
    printf '%s\n' 'Activate your configured Conda environment, or run scripts/setup.sh with Python 3.12+ first.' >&2
    exit 1
fi
"$SHIFT_RUNTIME_PYTHON" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ is required"'
export PYTHONDONTWRITEBYTECODE=1
export LANGSMITH_TRACING=false
export ANONYMIZED_TELEMETRY=false
export MLFLOW_DISABLE_AGENT_HINT=1
exec "$SHIFT_RUNTIME_PYTHON" app.py
