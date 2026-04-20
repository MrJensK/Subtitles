#!/bin/bash
set -e

VENV_DIR="$(dirname "$0")/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing dependencies..."
pip install -r "$(dirname "$0")/requirements.txt"

echo ""
echo "Starting SubTok..."
echo "Open http://localhost:8000 in your browser"
echo ""
python app.py
