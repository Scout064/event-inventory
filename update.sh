#!/bin/bash
# File: update.sh
# Usage: sudo ./update.sh

# --- Root Check ---
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run with root privileges."
  echo "Please use: sudo $0"
  exit 1
fi

# Find exactly where this script is running from
SCRIPT_DIR=$(dirname "$(realpath "$0")")
SRC_DIR="$SCRIPT_DIR/inventory_app"

APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/config.json"

echo "--- Starting Automated Deployment ---"

# Safety check: Ensure the app folder actually exists before proceeding
if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Source directory $SRC_DIR not found!"
    echo "Make sure inventory_app/ is in the same folder as this script."
    exit 1
fi

# 1. Safely copy new App Code
echo "Copying new files from $SRC_DIR to $APP_DIR..."
rsync -av --exclude="venv" \
          --exclude="config.json" \
          --exclude="static/qr_codes" \
          --exclude="uploads" \
          --exclude="*.sqlite" \
          --exclude="__pycache__" \
          "$SRC_DIR/" "$APP_DIR/"

# 2. Update Permissions
echo "Setting permissions to www-data:www-data..."
chown -R www-data:www-data "$APP_DIR"

# 3. Extract DB credentials using Python
echo "Reading database configuration..."
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_user'])")
DB_PASS=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_pass'])")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_name'])")
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_host'])")

# 4. Apply base schema
echo "Applying base schema..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

# 5. Check current DB version
# Using MAX(version) to ensure a single integer is returned even if rows were duplicated
CURRENT_VER=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -s -e "SELECT MAX(version) FROM schema_version;")

if [ -z "$CURRENT_VER" ] || [ "$CURRENT_VER" == "NULL" ]; then
    CURRENT_VER=1
fi

echo "Current DB Version: $CURRENT_VER"

# 6. Apply Migrations based on version
# Note: Ensure migrations.sql contains "INSERT INTO schema_version (version) VALUES (X);" at the end
if [ "$CURRENT_VER" -lt 2 ]; then
    echo "Upgrading Database to Version 2..."
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/migrations.sql"
    
    # Cleanup duplicate versions if they exist
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "DELETE FROM schema_version WHERE version < 2;"
fi

# 7. Reload WSGI App
echo "Restarting application..."
touch "$APP_DIR/wsgi.py"
echo "Restarting apache2..."
systemctl status apache2

echo "--- Deployment Finished Successfully. ---"
