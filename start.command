#!/bin/zsh

set -e
cd "${0:A:h}"

if [[ -x .venv/bin/python ]]; then
  SHADOWING_PYTHON=.venv/bin/python
else
  SHADOWING_PYTHON=python3
fi

exec "$SHADOWING_PYTHON" -m shadowing_app
