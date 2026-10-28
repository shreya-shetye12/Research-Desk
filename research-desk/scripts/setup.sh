#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
SHIFT_PYTHON="${SHIFT_PYTHON:-python3}"
"$SHIFT_PYTHON" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ is required"'
"$SHIFT_PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
