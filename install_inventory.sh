#!/bin/bash
set -euo pipefail

# --- Root Check ---
if [ "$EUID" -ne 0 ]; then 
  echo "❌ Error: This script must be run as root or with sudo."
  exit 1
fi

echo "=== Event Inventory Management System Installer ==="

# ---------------------------------------------------------
# 1. Configuration & User Inputs
# ---------------------------------------------------------
APP_DIR="/var/www/inventory"
SCRIPT_DIR=$(dirname "$(realpath "$0")")
SRC_DIR="$SCRIPT_DIR/inventory_app"

# Database Inputs
read -p "Database Host (e.g., 127.0.0.1): " DB_HOST
read -p "Database Name [inventory_db]: " DB_NAME
DB_NAME=${DB_NAME:-inventory_db}
read -p "Database User [inventory_user]: " DB_USER
DB_USER=${DB_USER:-inventory_user}
read -s -p "Database Password: " DB_PASS
echo ""

# Web Server Inputs
echo "--- Web Server Configuration ---"
read -p "Enter ServerName (e.g., inventory.yourdomain.com): " SERVER_NAME
read -p "Are you using an external reverse proxy? (y/n): " USE_REVERSE_PROXY

USE_CERTBOT="n"
if [[ "$USE_REVERSE_PROXY" =~ ^[Nn]$ ]]; then
    read -p "Use Certbot for Let's Encrypt SSL? (y/n): " USE_CERTBOT
fi

# ---------------------------------------------------------
# 2. Dependency Resolution
# ---------------------------------------------------------
echo "--- Installing Dependencies ---"
apt-get update

CORE_DEPS=("mariadb-server" "mariadb-client" "python3" "python3-pip" "python3-venv" "apache2" "libapache2-mod-wsgi-py3" "rsync" "libmariadb-dev" "libmariadb-dev-compat" "fonts-dejavu-core")
for pkg in "${CORE_DEPS[@]}"; do
    apt-get install -y "$pkg"
done

if [[ "$USE_CERTBOT" =~ ^[Yy]$ ]]; then
    apt-get install -y certbot python3-certbot-apache
fi

# ---------------------------------------------------------
# 3. MariaDB Hardening & Setup
# ---------------------------------------------------------
echo "--- Hardening MariaDB & Creating Database ---"
systemctl enable --now mariadb

# Secure MariaDB
mysql <<'SECUREMYSQL'
DELETE FROM mysql.global_priv WHERE User='';
DROP DATABASE IF EXISTS test;
DELETE FROM mysql.db WHERE Db='test' OR Db LIKE 'test\_%';
ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket;
FLUSH PRIVILEGES;
SECUREMYSQL

# Create DB and user
mysql <<EOF
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${DB_USER}'@'${DB_HOST}' IDENTIFIED BY '${DB_PASS}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'${DB_HOST}';
FLUSH PRIVILEGES;
EOF

# ---------------------------------------------------------
# 4. App Deployment
# ---------------------------------------------------------
echo "--- Deploying Application Files ---"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/static/qr_codes"
mkdir -p "$APP_DIR/uploads"

if [ ! -d "$SRC_DIR" ]; then
    echo "❌ Error: inventory_app folder not found at $SRC_DIR"
    exit 1
fi

# Copy app code
rsync -av "$SRC_DIR/" "$APP_DIR/"

# Create config.json
cat <<EOF > "$APP_DIR/config.json"
{
  "db_host": "$DB_HOST",
  "db_name": "$DB_NAME",
  "db_user": "$DB_USER",
  "db_pass": "$DB_PASS"
}
EOF

# Setup Virtual Environment
cd "$APP_DIR"
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Apply Schema & Migrations
echo "Applying base schema and checking migrations..."
mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" < "$APP_DIR/schema.sql"

# ---------------------------------------------------------
# 5. Apache Configuration
# ---------------------------------------------------------
echo "--- Configuring Apache ---"
a2enmod ssl rewrite headers proxy proxy_http
VHOST_CONF="/etc/apache2/sites-available/inventory.conf"

if [[ "$USE_REVERSE_PROXY" =~ ^[Yy]$ ]]; then
    # Simple WSGI VHost (SSL handled by proxy)
    tee "$VHOST_CONF" > /dev/null <<EOF
<VirtualHost *:80>
    ServerName $SERVER_NAME

    ErrorLog \${APACHE_LOG_DIR}/inventory_error.log
    CustomLog \${APACHE_LOG_DIR}/inventory_access.log combined

    WSGIDaemonProcess inventory_app python-home=$APP_DIR/venv python-path=$APP_DIR
    WSGIScriptAlias / $APP_DIR/wsgi.py
    <Directory $APP_DIR>
        Require all granted
    </Directory>
</VirtualHost>
EOF
else
    # LAN Bypass + Global HTTPS logic
    CERT_FILE="/etc/ssl/certs/ssl-cert-snakeoil.pem"
    KEY_FILE="/etc/ssl/private/ssl-cert-snakeoil.key"

    if [[ "$USE_CERTBOT" =~ ^[Yy]$ ]]; then
        certbot certonly --apache -d "$SERVER_NAME" --non-interactive --agree-tos -m "admin@$SERVER_NAME"
        CERT_FILE="/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem"
        KEY_FILE="/etc/letsencrypt/live/$SERVER_NAME/privkey.pem"
    fi

    tee "$VHOST_CONF" > /dev/null <<EOF
<VirtualHost *:80>
    ServerName $SERVER_NAME
    
    ErrorLog \${APACHE_LOG_DIR}/inventory_error.log
    CustomLog \${APACHE_LOG_DIR}/inventory_access.log combined

    RewriteEngine On
    # Allow local LAN (192.168.x.x) to stay on HTTP
    RewriteCond %{REMOTE_ADDR} !^192\.168\.
    RewriteRule ^/(.*)$ https://%{HTTP_HOST}/\$1 [R=301,L]

    DocumentRoot $APP_DIR
    WSGIDaemonProcess inventory_app_http python-home=$APP_DIR/venv python-path=$APP_DIR
    WSGIScriptAlias / $APP_DIR/wsgi.py
    <Directory $APP_DIR>
        Require all granted
    </Directory>
</VirtualHost>

<VirtualHost *:443>
    ServerName $SERVER_NAME

    ErrorLog \${APACHE_LOG_DIR}/inventory_error.log
    CustomLog \${APACHE_LOG_DIR}/inventory_access.log combined

    SSLEngine on
    SSLCertificateFile $CERT_FILE
    SSLCertificateKeyFile $KEY_FILE

    WSGIDaemonProcess inventory_app_https python-home=$APP_DIR/venv python-path=$APP_DIR
    WSGIScriptAlias / $APP_DIR/wsgi.py

    <Directory $APP_DIR>
        Require all granted
    </Directory>
</VirtualHost>
EOF
fi

# Set Permissions (Must happen after files are synced)
chown -R www-data:www-data "$APP_DIR"
chmod -R 750 "$APP_DIR"

a2ensite inventory.conf
a2dissite 000-default.conf || true
systemctl restart apache2

echo "========================================================="
echo "✅ Installation complete!"
echo "URL: http://$SERVER_NAME"
echo "Log Location: /var/log/apache2/inventory_error.log"
echo "========================================================="
