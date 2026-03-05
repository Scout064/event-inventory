#!/bin/bash
# File: update.sh
# Usage: sudo ./update.sh

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
# The trailing slash on "$SRC_DIR/" ensures we copy the contents, not the folder itself
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

# 4. Apply base schema (Ensure your schema.sql uses "CREATE TABLE IF NOT EXISTS")
echo "Applying base schema..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

# 5. Check current DB version
CURRENT_VER=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -s -e "SELECT version FROM schema_version;")

# Handle case where schema_version might be empty/null on first run
if [ -z "$CURRENT_VER" ]; then
    CURRENT_VER=1
fi

echo "Current DB Version: $CURRENT_VER"

# 6. Apply Migrations based on version
if [ "$CURRENT_VER" -lt 2 ]; then
    echo "Upgrading Database to Version 2..."
    # Run the migration file
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/migrations.sql"
    
    # Update the version number in the database after successful migration
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "UPDATE schema_version SET version = 2;"
fi

# 7. Reload WSGI App
echo "Restarting application..."
touch "$APP_DIR/wsgi.py"

echo "--- Deployment Finished Successfully. ---"
