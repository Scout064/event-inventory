v#!/bin/bash
# File: update.sh
# Usage: ./update.sh [branch_name]

# 1. Accept the branch from the Python subprocess, default to main
BRANCH=${1:-main}
APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/inventory_app/config.json"
VENV_PIP="$APP_DIR/inventory_app/venv/bin/pip"
BACKUP_DIR="$APP_DIR/inventory_app/backups"

echo "--- Starting Automated Deployment for Branch: $BRANCH ---"

# 2. Pull latest code from GitHub
# We assume $APP_DIR is a cloned git repository owned by the web user
echo "Pulling latest code for branch: $BRANCH..."
cd "$APP_DIR" || { echo "Failed to cd to $APP_DIR"; exit 1; }
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

# 3. Update Python Dependencies
if [ -f "$APP_DIR/inventory_app/requirements.txt" ]; then
    echo "Checking for new or missing Python modules..."
    $VENV_PIP install -r "$APP_DIR/inventory_app/requirements.txt"
fi

# 4. Extract DB Credentials
echo "Reading database credentials..."
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_host', 'localhost'))")
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_user', ''))")
DB_PASS=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_pass', ''))")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_name', ''))")

# 5. Database Backup & Retention (Keep last 2)
echo "Setting permissions and creating backup..."
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

echo "Creating database backup: $BACKUP_FILE..."
mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "Backup successful. Cleaning up old backups (Keeping last 2)..."
    cd "$BACKUP_DIR" && ls -1tr db_backup_*.sql | head -n -2 | xargs -r rm
    cd "$APP_DIR"
else
    echo "CRITICAL ERROR: Database backup failed. Aborting deployment for safety."
    exit 1
fi

# 6. Apply Schema & Migrations
echo "Applying base schema and checking migrations..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/inventory_app/schema.sql"

# Note: I left the rest of your specific migration logic out as it was cut off in the upload, 
# but you can safely paste your CURRENT_VER checks right here!

# 7. Restart Web Service
echo "Restarting application..."
touch "$APP_DIR/wsgi.py"
