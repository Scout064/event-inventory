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
SRC_DIR="$SCRIPT_DIR"
APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/inventory_app/config.json"
VENV_PIP="$APP_DIR/inventory_app/venv/bin/pip"
BACKUP_DIR="$APP_DIR/inventory_app/backups"
VENV_PYTHON="$APP_DIR/inventory_app/venv/bin/python3"

echo "--- Starting Automated Deployment ---"

# Safety check: Ensure the app folder exists
if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Source directory $SRC_DIR not found!"
    exit 1
fi

# Check if .env exists, if not create it
# Prepare .env file for secrets
SECRET_ENV="$APP_DIR/inventory_app/.env"
if [ ! -f "$SECRET_ENV" ]; then
    echo "Preparing .env..."
    tee "$SECRET_ENV" > /dev/null <<EOF
    # ------ ENV FILE FOR SECRETS ------ #
EOF
fi

# move contents from the existing ".json"
CONFIG_FILE="$APP_DIR/inventory_app/config.json"
TEMP_FILE="$APP_DIR/inventory_app/config.tmp.json"

# Check if the keys exist in the JSON file
# .db_pass != null and .encryption_key != null ensures both are present
if jq -e '.db_pass != null and .encryption_key != null' "$CONFIG_FILE" > /dev/null; then
    echo "Secrets detected. Starting migration..."

    # 1. Extract values to .env
    # We do this first so we don't lose the data!
    DB_PASS=$(jq -r '.db_pass' "$CONFIG_FILE")
    ENC_KEY=$(jq -r '.encryption_key' "$CONFIG_FILE")

    [[ -f "$SECRET_ENV" && -n "$(tail -c 1 "$SECRET_ENV" 2>/dev/null)" ]] && echo "" >> "$SECRET_ENV"
    echo "DB_PASS=\"$DB_PASS\"" >> "$SECRET_ENV"
    echo "ENCRYPTION_KEY=\"$ENC_KEY\"" >> "$SECRET_ENV"

    # 2. Delete the keys from config.json
    # del() takes multiple keys separated by commas
    jq 'del(.db_pass, .encryption_key)' "$CONFIG_FILE" > "$TEMP_FILE"

    # 3. Replace the original file with the cleaned version
    mv "$TEMP_FILE" "$CONFIG_FILE"

    # 4. Set secure permissions on .env (Owner read/write only)
    chown www-data:www-data "$SECRET_ENV"
    chmod 600 "$SECRET_ENV"
    
    echo "Success: Credentials moved to $SECRET_ENV and scrubbed from $CONFIG_FILE."
else
    echo "Migration skipped: 'db_pass' or 'encryption_key' not found in $CONFIG_FILE."
fi

# --- Update Systemd Service ---
SERVICE_FILE="/etc/systemd/system/inventory.service"
ENV_LINE="EnvironmentFile=/var/www/inventory/.env"

# Check if the service file exists before trying to modify it
if [ -f "$SERVICE_FILE" ]; then
    # Check if the EnvironmentFile line is already in the service file
    if grep -qF "$ENV_LINE" "$SERVICE_FILE"; then
        echo "Systemd service already configured with EnvironmentFile."
    else
        echo "Adding EnvironmentFile to systemd service..."
        # Use sed to append the line immediately after the [Service] tag
        sed -i '/^\[Service\]/a '"$ENV_LINE" "$SERVICE_FILE"
        
        # Reload systemd so it registers the change to the file
        systemctl daemon-reload
        echo "Systemd daemon reloaded."
    fi
else
    echo "Warning: Service file $SERVICE_FILE not found!"
fi

# 1. Safely copy new App Code
echo "Copying new files from $SRC_DIR to $APP_DIR..."
rsync -av \
  --include="inventory_app/***" \
  --include="wsgi.py" \
  --exclude="*" \
  "$SRC_DIR/" "$APP_DIR/"

# 2. Update Python Dependencies
if [ -f "$APP_DIR/inventory_app/requirements.txt" ]; then
    echo "Checking for new or missing Python modules..."
    $VENV_PIP install -r "$APP_DIR/inventory_app/requirements.txt"
fi

# 3. Update Permissions
echo "Setting permissions..."
mkdir -p "$BACKUP_DIR"
chown -R www-data:www-data "$APP_DIR"
chmod 750 "$BACKUP_DIR"

# 4. Extract DB credentials
echo "Reading database configuration..."

# Check if env exists, if not, abort
if [ ! -f "$SECRET_ENV" ]; then
    echo "ERROR: .env file not found at $SECRET_ENV. Cannot proceed!"
    exit 1
fi

# We use Python's dotenv library to read the password safely. 
# This prevents Bash from trying to interpret '$' inside double quotes.
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_user', ''))")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_name', ''))")
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_host', '127.0.0.1'))")

# Read from .env safely
DB_PASS=$($VENV_PYTHON -c "
import os
from dotenv import load_dotenv
load_dotenv('$SECRET_ENV')
print(os.getenv('DB_PASS', ''))
")

if [ -z "$DB_PASS" ]; then
    echo "CRITICAL ERROR: Could not read DB_PASS from .env"
    exit 1
fi

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
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/inventory_app/schema.sql"
# Get current DB version
CURRENT_VER=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -s -e "SELECT MAX(version) FROM schema_version;")
if [ -z "$CURRENT_VER" ] || [ "$CURRENT_VER" = "NULL" ]; then
    CURRENT_VER=1
fi
# Extract latest version from migrations.sql
LATEST_VER=$(grep -Eo '^-- VERSION [0-9]+' "$APP_DIR/inventory_app/migrations.sql" | awk '{print $3}' | sort -n | tail -1)
if [ -z "$LATEST_VER" ]; then
    echo "ERROR: Could not determine latest migration version"
    exit 1
fi
echo "Current DB version: $CURRENT_VER"
echo "Latest migration version: $LATEST_VER"
# Compare versions
if [ "$CURRENT_VER" -lt "$LATEST_VER" ]; then
    echo "Upgrading Database to Version $LATEST_VER..."
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/inventory_app/migrations.sql"
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" \
        -e "DELETE FROM schema_version WHERE version < $LATEST_VER;"
else
    echo "Database already up to date."
fi

# 7. Reload
echo "Restarting application and Apache..."
touch "$APP_DIR/wsgi.py"
systemctl restart inventory

echo "--- Deployment Finished Successfully. ---"
