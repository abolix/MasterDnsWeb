#!/usr/bin/env bash
set -euo pipefail

# ── Build MasterWeb single binary for Linux amd64 ──
# Run this ON a Linux amd64 machine (or WSL2).
# Prerequisites: Python 3.11+, Node.js 18+, npm

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR/frontend"

echo "==> Installing Node dependencies..."
npm ci

echo "==> Generating static frontend..."
npm run generate

cd "$ROOT_DIR"
echo "==> Copying static output to backend..."
node scripts/copy-static.mjs

echo "==> Setting up Python venv..."
python3 -m venv .buildenv
source .buildenv/bin/activate

echo "==> Installing Python dependencies..."
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install pyinstaller

echo "==> Building binary with PyInstaller..."
pyinstaller build.spec --distpath dist --workpath build_tmp --clean -y

echo "==> Cleaning up..."
rm -rf build_tmp .buildenv

BINARY="dist/masterweb"
if [ -f "$BINARY" ]; then
    chmod +x "$BINARY"
    FILE_SIZE=$(du -h "$BINARY" | cut -f1)
    echo ""
    echo "Build successful: $BINARY ($FILE_SIZE)"
    echo "Deploy to your server and run:  ./masterweb"
else
    echo "ERROR: Build failed – binary not found at $BINARY"
    exit 1
fi
