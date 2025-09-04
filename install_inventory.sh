#!/bin/bash
# Inventory Management System Setup Script (No sudo)
# Tested on Ubuntu/Debian-based systems

echo "=== Updating system packages ==="
apt update && apt upgrade -y

echo "=== Installing Apache2, mod_wsgi, Python, and MariaDB ==="
apt install -y apache2 libapache2-mod-wsgi-py3 python3 python3-venv python3-pip mariadb-server libmariadb3 libmariadb-dev

echo "=== Securing MariaDB installation ==="
mysql_secure_installation

echo "=== Enabling Apache modules ==="
a2enmod ssl
a2enmod wsgi
a2enmod rewrite
systemctl restart apache2

echo "=== Creating application directory and virtual environment ==="
APP_DIR="/var/www/inventory"
mkdir -p $APP_DIR
chown $(whoami):$(whoami) $APP_DIR
cd $APP_DIR
python3 -m venv venv
source venv/bin/activate

echo "=== Installing Python dependencies ==="
pip install flask flask-login flask-wtf pillow qrcode reportlab mariadb

echo "=== Installing Certbot for HTTPS ==="
apt install -y certbot python3-certbot-apache

echo "=== Database setup ==="
read -p "Enter MariaDB root password: " ROOT_PASS
read -p "Enter new database name [inventory_db]: " DB_NAME
read -p "Enter new database user [inventory_user]: " DB_USER
read -sp "Enter password for new database user: " DB_PASS
echo

DB_NAME=${DB_NAME:-inventory_db}
DB_USER=${DB_USER:-inventory_user}

mysql -u root -p$ROOT_PASS <<EOF
CREATE DATABASE IF NOT EXISTS $DB_NAME;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
EOF

echo "=== Setup complete ==="
echo "Next steps:"
echo "1. Copy your Flask app to $APP_DIR"
echo "2. Configure Apache VirtualHost for WSGI"
echo "3. Enable HTTPS using: certbot --apache -d yourdomain.com"
