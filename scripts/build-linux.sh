#!/usr/bin/env bash
set -euo pipefail

# ── Build MasterDnsWeb release package for Linux amd64 ──
# Run this ON a Linux amd64 machine (or WSL2).
# Prerequisites: Python 3.11+, Node.js 18+, npm
#
# The MasterDnsVPN binary is looked up in this order:
#   1. backend/bin/MasterDnsVPN   (dev default — drop it here)
#   2. Path set by MASTERDNSVPN_BINARY env var
#
# Output: dist/MasterDnsWeb-linux-amd64.tar.gz
#   MasterDnsWeb/
#     MasterDnsWeb      ← web panel binary
#     MasterDnsVPN      ← VPN client binary
#     .env              ← sample config (edit before running)

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

echo "==> Cleaning up build artifacts..."
rm -rf build_tmp .buildenv

BINARY="dist/MasterDnsWeb"
if [ ! -f "$BINARY" ]; then
    echo "ERROR: Build failed – binary not found at $BINARY"
    exit 1
fi
chmod +x "$BINARY"

# ── Locate MasterDnsVPN binary ──
VPN_BINARY=""
if [ -f "$ROOT_DIR/backend/bin/MasterDnsVPN" ]; then
    VPN_BINARY="$ROOT_DIR/backend/bin/MasterDnsVPN"
elif [ -n "${MASTERDNSVPN_BINARY:-}" ] && [ -f "${MASTERDNSVPN_BINARY}" ]; then
    VPN_BINARY="${MASTERDNSVPN_BINARY}"
fi

# ── Assemble release folder ──
RELEASE_NAME="MasterDnsWeb"
RELEASE_DIR="dist/release/$RELEASE_NAME"
RELEASE_ARCHIVE="dist/MasterDnsWeb-linux-amd64.tar.gz"

rm -rf "dist/release"
mkdir -p "$RELEASE_DIR"

cp "$BINARY" "$RELEASE_DIR/MasterDnsWeb"
chmod +x "$RELEASE_DIR/MasterDnsWeb"

if [ -n "$VPN_BINARY" ]; then
    cp "$VPN_BINARY" "$RELEASE_DIR/MasterDnsVPN"
    chmod +x "$RELEASE_DIR/MasterDnsVPN"
    echo "==> Included MasterDnsVPN from: $VPN_BINARY"
else
    echo ""
    echo "WARNING: MasterDnsVPN binary not found."
    echo "  Place it at backend/bin/MasterDnsVPN, or set the MASTERDNSVPN_BINARY env var."
    echo "  The release archive will be created without it – add it manually before deploying."
    echo ""
fi

# Generate a random secret key for the .env template
GENERATED_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > "$RELEASE_DIR/.env" << EOF
# MasterDnsWeb — Configuration
# Edit this file, then run:  sudo ./MasterDnsWeb
#
# MasterDnsWeb MUST run as root (or with sudo) to manage systemd services.

# ── Web panel access ──────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# Random secret used to sign login sessions.
# A unique value has been generated for you — do not share it.
SECRET_KEY=${GENERATED_SECRET}

# ── Network ───────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000

# Set to true if you are using HTTPS (e.g. behind nginx with SSL)
COOKIE_SECURE=false

# ── Service settings ──────────────────────────────────────
MASTERVPN_SERVICE_USER=root
MASTERVPN_SERVICE_RESTART=always
MASTERVPN_SERVICE_RESTART_SEC=5
# Override only if MasterDnsVPN is not in the same folder as MasterDnsWeb:
# MASTERVPN_SERVICE_EXEC_START=/path/to/MasterDnsVPN
EOF

tar -czf "$RELEASE_ARCHIVE" -C "dist/release" "$RELEASE_NAME"
rm -rf "dist/release"

ARCHIVE_SIZE=$(du -h "$RELEASE_ARCHIVE" | cut -f1)
echo ""
echo "Release archive: $RELEASE_ARCHIVE ($ARCHIVE_SIZE)"
echo ""
echo "Deploy:"
echo "  tar -xzf MasterDnsWeb-linux-amd64.tar.gz"
echo "  cd MasterDnsWeb"
echo "  nano .env              # set ADMIN_PASSWORD — everything else has safe defaults"
echo "  sudo ./MasterDnsWeb    # must run as root to manage systemd services"
echo ""
echo "  Folder layout after first run:"
echo "    MasterDnsWeb/"
echo "      MasterDnsWeb   ← web panel binary"
echo "      MasterDnsVPN   ← VPN client binary"
echo "      .env           ← your config"
echo "      data/          ← instance profiles (auto-created)"
echo "      runtime/       ← per-instance working dirs (auto-created)"
