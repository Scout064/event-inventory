#!/bin/bash
# File: /var/www/inventory/update.sh

APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/config.json"

echo "--- Starting Automated Deployment ---"
cd $APP_DIR

# 1. Pull latest changes (if using Git)
# git pull origin main

# 2. Extract DB credentials using Python (since jq might not be installed)
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_user'])")
DB_PASS=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_pass'])")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_name'])")
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['db_host'])")

# 1. Apply base schema (Always safe)
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

# 2. Check current version
CURRENT_VER=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -s -e "SELECT version FROM schema_version;")

echo "Current DB Version: $CURRENT_VER"

# 3. Apply Migrations based on version
if [ "$CURRENT_VER" -lt 2 ]; then
    echo "Upgrading to Version 2..."
    # You can either point to a specific file or run a string
    #mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "ALTER TABLE items ADD COLUMN IF NOT EXISTS price DECIMAL(10,2) DEFAULT 0.00; UPDATE schema_version SET version = 2;"
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/migrations.sql"
fi

# if [ "$CURRENT_VER" -lt 3 ]; then ... upgrade logic ... fi

# 4. Reload App
touch "$APP_DIR/wsgi.py"
echo "--- Deployment Finished. ---"
