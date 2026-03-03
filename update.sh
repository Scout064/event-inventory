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

# 3. Apply Schema.sql
echo "Applying database schema..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

# 4. Update Python Environment
echo "Updating dependencies..."
source venv/bin/activate
pip install -r requirements.txt

# 5. Trigger Apache Reload
# Touching wsgi.py tells mod_wsgi to restart the application on the next request
echo "Reloading Flask application..."
touch "$APP_DIR/wsgi.py"

echo "--- Deployment Successful ---"
