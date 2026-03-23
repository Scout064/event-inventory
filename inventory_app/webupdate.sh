#!/bin/bash
# File: webupdate.sh
# Usage: ./webupdate.sh [branch_name]

# 1. Set up Logging and absolute path
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LOG_FILE="/var/log/apache2/inventory_webupdate.log"
# This line pipes all subsequent stdout and stderr to tee, 
# appending to the log file while still printing to the screen/frontend.
exec > >(/usr/bin/tee -a "$LOG_FILE") 2>&1

echo "============================================================"
echo "--- Starting Automated Deployment at $(date) ---"

# 2. Accept the branch from the Python subprocess, default to main
BRANCH=${1:-main}
APP_DIR="/var/www/inventory"
CONFIG_FILE="$APP_DIR/inventory_app/config.json"
VENV_PIP="$APP_DIR/inventory_app/venv/bin/pip"
BACKUP_DIR="$APP_DIR/inventory_app/backups"

echo "Target Branch: $BRANCH"

# 2.1 prepare switch to .env if not already done
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

# 3. Extract DB Credentials
echo "Preparing Database for the update..."
echo "Reading database credentials..."
DB_HOST=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_host', 'localhost'))")
DB_USER=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_user', ''))")
DB_NAME=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('db_name', ''))")
DB_PASS=$(grep '^DB_PASS=' "$SECRET_ENV" | cut -d '=' -f2- | sed 's/^"//;s/"$//')

# 4. Database Backup & Retention
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
    echo "see the output of this run here:"
    echo "sudo cat /var/log/apache2/inventory_webupdate.log"
    sleep 15
    exit 1
fi

# 5. Pull latest code from GitHub
echo "Pulling latest code..."
cd "$APP_DIR" || { echo "Failed to cd to $APP_DIR"; exit 1; }
REPO_URL="https://github.com/Scout064/event-inventory.git"
CURRENT_URL=$(git remote get-url origin 2>/dev/null)
if [ "$CURRENT_URL" != "$REPO_URL" ]; then
  echo "Setting remote URL..."
  git remote set-url origin "$REPO_URL"
else
  echo "Remote URL already set. Skipping..."
fi
git stash
git fetch origin
git checkout "$BRANCH"
git pull origin "$BRANCH"

# 6. Update Python Dependencies
if [ -f "$APP_DIR/inventory_app/requirements.txt" ]; then
    echo "Checking for new or missing Python modules..."
    $VENV_PIP install -r "$APP_DIR/inventory_app/requirements.txt"
fi

# 7. Apply Schema & Migrations
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

# 8. Restart Web Service
echo "Restarting application..."
touch "$APP_DIR/wsgi.py"
sudo /usr/bin/systemctl restart inventory
sleep 5
if systemctl is-active --quiet inventory; then
    echo "--- Deployment Complete ---"
    echo "You can find the output of this run under:"
    echo "/var/log/apache2/inventory_webupdate.log"
    echo "sudo cat /var/log/apache2/inventory_webupdate.log"
    echo "Gunicorn Logs: sudo journalctl -u inventory -f"
    sleep 15
else
    echo "Deployment FAILED: Check logs with 'sudo journalctl -u inventory -f'"
    sleep 15
    exit 1
fi
