#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [ -x ".venv311/bin/python" ]; then
  exec .venv311/bin/python -m app.desktop_app
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "The project virtual environment was not found."
  echo "Run: python3.11 -m venv .venv311 && . .venv311/bin/activate && pip install -r requirements.txt"
  exit 1
fi

exec .venv/bin/python -m app.desktop_app
