[![Python CI - Event Inventory](https://github.com/Scout064/event-inventory/actions/workflows/python-app.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/python-app.yml)
[![CodeQL Advanced](https://github.com/Scout064/event-inventory/actions/workflows/codeql.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/codeql.yml)
[![Dependabot Updates](https://github.com/Scout064/event-inventory/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/dependabot/dependabot-updates)
[![Dependency review](https://github.com/Scout064/event-inventory/actions/workflows/dependency-review.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/dependency-review.yml)

# event-inventory
"Event Inventory" is a very lightweight Flask App to manage your Event Inventory (subtle, I know ;))

# 🎛 Inventory Management System for Event Technicians

A **web-based inventory management system** built with **Python (Flask)**, **MariaDB**, and **Gunicorn** behind **Apache2**.
Designed for **event technicians** to manage equipment, productions, and generate reports with QR code labels.

---

## ✅ Features

* Initial **setup wizard** (database, admin account, company logo)
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
git clone https://github.com/Scout064/event-inventory.git
cd event-inventory
```

### 2. Run Installation Script

Make sure you are on **Linux** with `apt-get` available and run the script as **root** or with **sudo**.

```bash
chmod +x install_inventory.sh
./install_inventory.sh
```

This will:

* Install Python, Apache2, mod\_wsgi
* Install MariaDB client libraries
* Create a virtual environment
* Install all Python dependencies

move the contents of `inventory_app` to `/var/www/inventory` 

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

LGPL-2.1 license

---
