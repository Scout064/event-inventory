#!/bin/bash
# prepare-docker.sh
# Run once on the host before 'docker compose up'.
# Creates the directory structure, empty config files, and generates
# all secrets needed by docker-compose.yml.
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
# Write default config so the app can start before setup is complete
sudo tee "$TARGET_DIR/inventory_app/config.json" > /dev/null << 'EOF'
{
  "configured": false,
  "app_domain": "",
  "db_host": "",
  "db_port": "",
  "db_name": "",
  "db_user": "",
  "logo_path": "",
  "site_name": ""
}
EOF
sudo touch "$TARGET_DIR/inventory_app/.env"

sudo chown -R "$USER:$USER" "$TARGET_DIR"
chmod 775 "$TARGET_DIR"

# ─── Generate Watchtower API Token ────────────────────────────────────────────
# Written to the ROOT .env ($TARGET_DIR/.env), not the app .env.
#
# Docker Compose reads $TARGET_DIR/.env automatically for ${VAR} substitution
# in docker-compose.yml. The app-level secrets (DB_PASS, ENCRYPTION_KEY etc.)
# live separately in $TARGET_DIR/inventory_app/.env and are never exposed to
# the compose layer.
#
# openssl rand -hex 32 = 256 bits of entropy (NIST SP 800-131A compliant).
ROOT_ENV="$TARGET_DIR/.env"
APP_ENV="$TARGET_DIR/inventory_app/.env"

if grep -qF "WATCHTOWER_TOKEN=" "$ROOT_ENV" 2>/dev/null; then
    echo "--- WATCHTOWER_TOKEN already present in $ROOT_ENV, skipping generation ---"
else
    WATCHTOWER_TOKEN=$(openssl rand -hex 32)
    echo "WATCHTOWER_TOKEN=$WATCHTOWER_TOKEN" >> "$ROOT_ENV"
    echo "--- Watchtower API token generated ---"
fi

# ─── Secure both secrets files ────────────────────────────────────────────────
# 600 = owner read/write only. No group, no world access.
chmod 600 "$ROOT_ENV"
chmod 600 "$APP_ENV"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "--- Done ---"
echo ""
echo "File layout:"
echo "  $ROOT_ENV          <- WATCHTOWER_TOKEN (read by Docker Compose)"
echo "  $APP_ENV   <- DB_PASS, ENCRYPTION_KEY  (read by the app)"
echo ""
echo "Next steps:"
echo "  1. Place docker-compose.yml in: $TARGET_DIR"
echo "  2. cd $TARGET_DIR && docker compose up -d"
echo "  3. Visit http://<host>:8000/setup to configure the app"
echo ""
echo "To view your generated token (keep this private):"
echo "  grep WATCHTOWER_TOKEN $ROOT_ENV"
