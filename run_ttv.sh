#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "❌ Virtual environment not found. Run: bash setup.sh"
    exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate"

if [ "$1" = "--test" ]; then
    shift
    exec python -m pytest "$SCRIPT_DIR/tests/" "$@"
fi

exec python -m talk_to_vibe "$@"
