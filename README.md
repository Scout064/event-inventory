# event-inventory
"Event Inventory" is a very lightweight Flask App to manage your Event Inventory (subtle, I know ;))

# 🎛 Inventory Management System for Event Technicians

A **web-based inventory management system** built with **Python (Flask)**, **MariaDB**, and **Apache2**.
Designed for **event technicians** to manage equipment, productions, and generate reports with QR code labels.

---

## ✅ Features

* Initial **setup wizard** (database, admin account, company logo)
* **HTTPS enforced** (except for local LAN access)
* **Admin & User login** system
* Manage:

  * Items (name, category, unique ID, description, serial number, location, manufacturer, model)
  * Locations / Productions
* Generate:

  * **Reports**
  * **Bills of Materials (BOM)** for productions
* Print **QR code labels with your logo** (Dymo-compatible)
* Export **PDF reports** and print production lists

---

## 🛠 Technology Stack

* **Backend**: Flask (Python)
* **Database**: MariaDB
* **Web Server**: Apache2 + mod\_wsgi
* **UI**: Bootstrap (minimal)
* **PDF Generation**: ReportLab
* **QR Codes**: qrcode + Pillow

---

## 📦 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR-USERNAME/inventory-management.git
cd inventory-management
```

### 2. Run Installation Script

Make sure you are on **Linux** with `apt-get` available and run the script as **root** or with **sudo**.

```bash
chmod +x install_dependencies.sh
./install_dependencies.sh
```

This will:

* Install Python, Apache2, mod\_wsgi
* Install MariaDB client libraries
* Create a virtual environment
* Install all Python dependencies

move the contents of `inventory_app` to `/var/www/inventory` 

### 3. Configure Apache2 (Production)

Use the provided `apache-inventory.conf` as a template for your VirtualHost:

```apache
<VirtualHost *:443>
    ServerName yourdomain.com
    DocumentRoot /var/www/inventory
    WSGIScriptAlias / /var/www/inventory/wsgi.py

    <Directory /var/www/inventory>
        Require all granted
    </Directory>

    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/your-cert.pem
    SSLCertificateKeyFile /etc/ssl/private/your-key.pem
</VirtualHost>
```

### 4. Development Mode

```bash
cd /var/www/inventory
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Access via:
`http://127.0.0.1:8000` / `http://server-ip:8000` to complete the initial configuration.

---

## 🖨 Printing Labels

The system supports **QR code labels** with your logo for Dymo printers.
Use `lp` or CUPS for printing:

```bash
lp -d DYMO_LabelWriter_450 label.pdf
```

---

## 🔐 Security

* Enforces **HTTPS** except for LAN clients
* Passwords are hashed (Flask-Login + Werkzeug)
* CSRF protection enabled via Flask-WTF

---

## 📄 License

This software is **proprietary**.
See [LICENSE.txt](license.txt) for details.

---

## 📬 Contact

**Mössner – IT und Audio**
[info@moessner-audio.de](mailto:info@moessner-audio.de)
