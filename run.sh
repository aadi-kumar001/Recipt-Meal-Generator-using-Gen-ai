#!/usr/bin/env bash
# Usage: ./run.sh   (optionally: export ANTHROPIC_API_KEY=... first)
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
python app.py
