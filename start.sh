#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Run ./install.sh first."
    exit 1
fi

source "$VENV_DIR/bin/activate"

echo "Starting SubTok..."
echo "Open http://localhost:8000 in your browser"
echo ""
cd "$DIR"
python app.py
