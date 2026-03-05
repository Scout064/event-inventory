#!/bin/bash
# File: update.sh
# Usage: sudo ./update.sh

# --- Root Check ---
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run with root privileges."
  echo "Please use: sudo $0"
  exit 1
fi

# Find paths
SCRIPT_DIR=$(dirname "$(realpath "$0")")
SRC_DIR="$SCRIPT_DIR/inventory_app"
APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/config.json"
VENV_PIP="$APP_DIR/venv/bin/pip"
BACKUP_DIR="$APP_DIR/backups"

echo "--- Starting Automated Deployment ---"

# Safety check: Ensure the app folder exists
if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Source directory $SRC_DIR not found!"
    exit 1
fi

# 1. Safely copy new App Code
echo "Copying new files from $SRC_DIR to $APP_DIR..."
rsync -av --exclude="venv" \
          --exclude="config.json" \
          --exclude="static/qr_codes" \
          --exclude="uploads" \
          --exclude="backups" \
          --exclude="*.sqlite" \
          --exclude="__pycache__" \
          "$SRC_DIR/" "$APP_DIR/"

# 2. Update Python Dependencies
if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Checking for new or missing Python modules..."
    $VENV_PIP install -r "$APP_DIR/requirements.txt"
fi

# 3. Update Permissions
echo "Setting permissions..."
mkdir -p "$BACKUP_DIR"
chown -R www-data:www-data "$APP_DIR"
chmod 750 "$BACKUP_DIR"

# 4. Extract DB credentials
echo "Reading database configuration..."
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_user'])")
DB_PASS=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_pass'])")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_name'])")
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_host'])")

# 5. Database Backup & Retention (Keep last 2)
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

echo "Creating database backup: $BACKUP_FILE..."
mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup successful. Cleaning up old backups (Keeping last 2)..."
    # ls -1tr lists oldest first. head -n -2 selects all EXCEPT the 2 newest.
    cd "$BACKUP_DIR" && ls -1tr db_backup_*.sql | head -n -2 | xargs -r rm
    cd "$SCRIPT_DIR"
else
    echo "CRITICAL ERROR: Database backup failed. Aborting deployment for safety."
    exit 1
fi

# 6. Apply Schema & Migrations
echo "Applying base schema and checking migrations..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

CURRENT_VER=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -s -e "SELECT MAX(version) FROM schema_version;")
[ -z "$CURRENT_VER" ] || [ "$CURRENT_VER" == "NULL" ] && CURRENT_VER=1

if [ "$CURRENT_VER" -lt 2 ]; then
    echo "Upgrading Database to Version 2..."
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/migrations.sql"
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "DELETE FROM schema_version WHERE version < 2;"
fi

# 7. Reload
echo "Restarting application and Apache..."
touch "$APP_DIR/wsgi.py"
systemctl restart apache2

echo "--- Deployment Finished Successfully. ---"
