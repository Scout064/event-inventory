#!/bin/bash
# prepare-docker.sh
# Run once on the host before 'docker compose up'.
# Creates the directory structure, empty config files, and generates
# all secrets that docker-compose.yml needs via variable substitution.
set -e

DEFAULT_DIR="/srv/inventory"

echo "Where should the project root live? (default: $DEFAULT_DIR)"
read -r USR_DIR
TARGET_DIR="${USR_DIR:-$DEFAULT_DIR}"

echo "--- Preparing $TARGET_DIR ---"

sudo mkdir -p "$TARGET_DIR/inventory_app"

# Touch config files as root, then hand ownership to current user.
# These must exist as FILES before docker compose up — if they don't exist,
# Docker creates them as directories, which causes a confusing crash.
sudo touch "$TARGET_DIR/inventory_app/config.json"
sudo touch "$TARGET_DIR/inventory_app/.env"

sudo chown -R "$USER:$USER" "$TARGET_DIR"
chmod 775 "$TARGET_DIR"

# ─── Generate Watchtower API Token ────────────────────────────────────────────
# openssl rand -hex 32 produces 64 characters of cryptographically secure
# random hex — equivalent to 256 bits of entropy, meeting NIST SP 800-131A
# requirements for secret tokens.
ENV_FILE="$TARGET_DIR/inventory_app/.env"

if grep -qF "WATCHTOWER_TOKEN=" "$ENV_FILE" 2>/dev/null; then
    echo "--- WATCHTOWER_TOKEN already present in .env, skipping generation ---"
else
    WATCHTOWER_TOKEN=$(openssl rand -hex 32)
    echo "WATCHTOWER_TOKEN=$WATCHTOWER_TOKEN" >> "$ENV_FILE"
    echo "--- Watchtower API token generated and written to .env ---"
fi

# ─── Secure the secrets file ──────────────────────────────────────────────────
# 600 = owner read/write only. No group, no world access.
# This is the minimum permission for any file containing secrets.
chmod 600 "$ENV_FILE"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "--- Done ---"
echo "Your token has been written to: $ENV_FILE"
echo ""
echo "Next steps:"
echo "  1. Place docker-compose.yml in:   $TARGET_DIR"
echo "  2. cd $TARGET_DIR && docker compose up -d"
echo "  3. Visit http://<host>:8000/setup to configure the app"
echo ""
echo "To view your generated token (keep this private):"
echo "  grep WATCHTOWER_TOKEN $ENV_FILE"
