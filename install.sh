#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r "$DIR/requirements.txt"

echo ""

# Check ffmpeg
FFMPEG_OK=false
for candidate in "$(which ffmpeg 2>/dev/null)" "/opt/homebrew/bin/ffmpeg" "/usr/local/bin/ffmpeg"; do
    [ -z "$candidate" ] && continue
    [ -x "$candidate" ] || continue
    if "$candidate" -buildconf 2>&1 | grep -q 'enable-libass'; then
        echo "✓ ffmpeg with libass found at $candidate"
        FFMPEG_OK=true
        break
    fi
done

if [ "$FFMPEG_OK" = false ]; then
    echo ""
    echo "⚠  ffmpeg with libass not found — subtitle burning will fail."
    echo "   Fix: brew install ffmpeg"
    echo "   Then re-run this script."
fi

echo ""
echo "Done! Run ./start.sh to launch SubTok."
