#!/bin/bash
set -e

# ─── Paths ────────────────────────────────────────────────────────────────────
# APP_DIR matches WORKDIR in the Dockerfile (/inventory_app)
APP_DIR="${APP_DIR:-/inventory_app}"
INVENTORY_DIR="$APP_DIR/inventory_app"
CONFIG_JSON="$INVENTORY_DIR/config.json"
SECRET_ENV="$INVENTORY_DIR/.env"
SCHEMA_FILE="$INVENTORY_DIR/schema.sql"
MIGRATIONS_FILE="$INVENTORY_DIR/migrations.sql"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"

mkdir -p "$BACKUP_DIR"

# ─── Validate Prerequisites ───────────────────────────────────────────────────
# Note: No venv in Docker — packages are installed system-wide by the Dockerfile.
# We only check for the config files the app actually needs at runtime.
for FILE in "$CONFIG_JSON" "$SECRET_ENV"; do
    if [ ! -f "$FILE" ]; then
        echo "[entrypoint] CRITICAL ERROR: Required file not found: $FILE"
        echo "[entrypoint] Did you run prepare-docker.sh before starting the container?"
        exit 1
    fi
done

# ─── Check if app has been configured via /setup ─────────────────────────────
# config.json exists but may be empty (fresh install via prepare-docker.sh)
# or missing "configured": true. In that case, skip all DB steps and boot
# directly so the user can reach /setup to initialize the app.
IS_CONFIGURED=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$CONFIG_JSON'))
    print('yes' if cfg.get('configured') is false else 'no')
except Exception:
    print('no')
")

if [ "$IS_CONFIGURED" != "yes" ]; then
    echo "[entrypoint] App not configured yet. Skipping DB steps."
    echo "[entrypoint] Visit http://<host>:8000/setup to initialize the app."
    exec gunicorn \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        "wsgi:application"
fi

# ─── One-Time Secret Migration (config.json → .env) ──────────────────────────
# If db_pass is still in config.json, move it out safely.
# This handles the upgrade case where an old install still has secrets in JSON.
if python3 -c "
import json, sys
cfg = json.load(open('$CONFIG_JSON'))
sys.exit(0 if 'db_pass' in cfg else 1)
" 2>/dev/null; then
    echo "[entrypoint] Secrets detected in config.json. Migrating to .env..."

    DB_PASS_MIGRATE=$(python3 -c "
import json; cfg = json.load(open('$CONFIG_JSON')); print(cfg.get('db_pass', ''))
")

    # Append to .env only if the key is not already present
    grep -qF "DB_PASS=" "$SECRET_ENV" || echo "DB_PASS='$DB_PASS_MIGRATE'" >> "$SECRET_ENV"

    # Scrub secrets from config.json
    python3 -c "
import json
cfg = json.load(open('$CONFIG_JSON'))
cfg.pop('db_pass', None)
json.dump(cfg, open('$CONFIG_JSON', 'w'), indent=2)
"
    echo "[entrypoint] Migration complete. Secrets scrubbed from config.json."
fi

# ─── Read DB Credentials ──────────────────────────────────────────────────────
# Keys are lowercase (db_host, db_user, db_name) — this matches what db.py
# reads and what the setup form writes into config.json.
#
# Note: FLASK_SECRET_KEY is intentionally NOT validated here.
# crypto.py generates and writes it to .env lazily on first use — the app
# owns that lifecycle entirely.
echo "[entrypoint] Reading database configuration..."

DB_HOST=$(python3 -c "
import json, sys
try:
    with open('$CONFIG_JSON') as f: print(json.load(f)['db_host'])
except Exception as e: sys.stderr.write(f'ERROR: {e}\n'); sys.exit(1)
")

DB_USER=$(python3 -c "
import json, sys
try:
    with open('$CONFIG_JSON') as f: print(json.load(f)['db_user'])
except Exception as e: sys.stderr.write(f'ERROR: {e}\n'); sys.exit(1)
")

DB_NAME=$(python3 -c "
import json, sys
try:
    with open('$CONFIG_JSON') as f: print(json.load(f)['db_name'])
except Exception as e: sys.stderr.write(f'ERROR: {e}\n'); sys.exit(1)
")

DB_PASS=$(python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('$SECRET_ENV')
print(os.getenv('DB_PASS', ''))
")

for VAR_NAME in DB_HOST DB_USER DB_NAME DB_PASS; do
    if [ -z "${!VAR_NAME}" ]; then
        echo "[entrypoint] CRITICAL ERROR: Could not read $VAR_NAME — check config.json / .env"
        exit 1
    fi
done

echo "[entrypoint] Credentials loaded. Host=$DB_HOST, DB=$DB_NAME, User=$DB_USER"

# ─── Helper ───────────────────────────────────────────────────────────────────
mysql_cmd() {
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" "$@"
}

# ─── Wait for DB ──────────────────────────────────────────────────────────────
echo "[entrypoint] Waiting for database..."
MAX_TRIES=30
TRIES=0
until mysql_cmd -e "SELECT 1;" &>/dev/null; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge "$MAX_TRIES" ]; then
        echo "[entrypoint] CRITICAL ERROR: Database not ready after $MAX_TRIES attempts."
        exit 1
    fi
    echo "[entrypoint]   Not ready, retrying in 2s... ($TRIES/$MAX_TRIES)"
    sleep 2
done
echo "[entrypoint] Database is ready."

# ─── Backup ───────────────────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"
echo "[entrypoint] Creating backup: $BACKUP_FILE..."

if mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" > "$BACKUP_FILE"; then
    echo "[entrypoint] Backup successful. Pruning old backups (keeping last 2)..."
    cd "$BACKUP_DIR" && ls -1tr db_backup_*.sql 2>/dev/null | head -n -2 | xargs -r rm --
    cd "$APP_DIR"
else
    echo "[entrypoint] CRITICAL ERROR: Backup failed. Aborting to protect data."
    rm -f "$BACKUP_FILE"
    exit 1
fi

# ─── Apply Base Schema (only if not already present) ─────────────────────────
# Uses the existence of the schema_version table as a sentinel.
# schema.sql is safe to skip on restarts — it only needs to run once on a
# fresh database. Migrations handle all subsequent changes.
if [ ! -f "$SCHEMA_FILE" ]; then
    echo "[entrypoint] WARNING: No schema.sql found at $SCHEMA_FILE, skipping."
else
    SCHEMA_EXISTS=$(mysql_cmd -N -s -e "
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = '$DB_NAME'
        AND table_name = 'schema_version';
    ")

    if [ "$SCHEMA_EXISTS" -eq 0 ]; then
        echo "[entrypoint] schema_version table not found. Applying base schema..."
        mysql_cmd < "$SCHEMA_FILE"
        echo "[entrypoint] Base schema applied."
    else
        echo "[entrypoint] Schema already present. Skipping schema.sql."
    fi
fi

# ─── Apply Migrations (runs on every startup, skips if already current) ───────
if [ ! -f "$MIGRATIONS_FILE" ]; then
    echo "[entrypoint] No migrations.sql found, skipping."
else
    CURRENT_VER=$(mysql_cmd -N -s -e \
        "SELECT COALESCE(MAX(version), 1) FROM schema_version;" 2>/dev/null || echo "1")

    LATEST_VER=$(grep -Eo '^-- VERSION [0-9]+' "$MIGRATIONS_FILE" \
        | awk '{print $3}' | sort -n | tail -1)

    if [ -z "$LATEST_VER" ]; then
        echo "[entrypoint] CRITICAL ERROR: Could not determine latest migration version."
        exit 1
    fi

    echo "[entrypoint] DB version: current=$CURRENT_VER, latest=$LATEST_VER"

    if [ "$CURRENT_VER" -lt "$LATEST_VER" ]; then
        echo "[entrypoint] Upgrading to version $LATEST_VER..."
        mysql_cmd < "$MIGRATIONS_FILE"
        mysql_cmd -e "DELETE FROM schema_version WHERE version < $LATEST_VER;"
        echo "[entrypoint] Migration complete."
    else
        echo "[entrypoint] Database already up to date."
    fi
fi

# ─── Start Application ────────────────────────────────────────────────────────
echo "[entrypoint] All pre-flight checks passed. Starting gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    "wsgi:application"
