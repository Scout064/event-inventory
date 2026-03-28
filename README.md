[![Python CI - Event Inventory](https://github.com/Scout064/event-inventory/actions/workflows/python-app.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/python-app.yml)
[![CodeQL Advanced](https://github.com/Scout064/event-inventory/actions/workflows/codeql.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/codeql.yml)
[![Dependabot Updates](https://github.com/Scout064/event-inventory/actions/workflows/dependabot/dependabot-updates/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/dependabot/dependabot-updates)
[![Dependency review](https://github.com/Scout064/event-inventory/actions/workflows/dependency-review.yml/badge.svg)](https://github.com/Scout064/event-inventory/actions/workflows/dependency-review.yml)
[![Build and Push Docker Image](https://github.com/Scout064/event-inventory/actions/workflows/release-docker.yml/badge.svg?branch=main)](https://github.com/Scout064/event-inventory/actions/workflows/release-docker.yml)

# Event Inventory

> Self-hosted inventory management system for event and production equipment

---

## 🚀 Overview

**Event Inventory** is a web-based application designed for managing equipment used in events and productions. It enables teams to track inventory, manage productions, generate reports, and administrate users in a secure, self-hosted environment.

---

## ✨ Features

* 📦 Inventory management (items, categories, search)
* 🎬 Production tracking (assign equipment to events)
* 👥 User management & authentication
* 📊 Reporting & exports
* 🔎 Advanced search
* 🏷️ QR/label support
* ⚙️ Admin configuration panel

---

## 🏗️ Tech Stack

* **Backend:** Python (Flask)
* **Database:** MariaDB / MySQL
* **Frontend:** Jinja2 templates
* **Containerization:** Docker
* **CI/CD:** GitHub Actions

---

## 📦 Project Structure

```
inventory_app/
├── app.py              # Main app
├── db.py               # Database layer
├── reports.py          # Reporting
├── security.py         # Auth & security
├── templates/          # HTML templates
├── schema.sql          # DB schema
```

---

## ⚙️ Installation

### Option A — Docker (recommended)

#### Install Prerequisites for Docker Deployment
```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
```

##### (Optional) Run without sudo
```bash
sudo usermod -aG docker $USER
newgrp docker
```

##### Verify installation
```bash
docker --version
docker-compose version
```

##### Grab the "prepare-docker.sh"
This will setup the Docker environment for the App

[download](https://github.com/Scout064/event-inventory/blob/main/prepare-docker.sh)
```bash
sudo chmod +x ./prepare-docker.sh
./prepare-docker.sh
```

#### Via Docker Compose (Optional)

##### Get the docker-compose.yml
Grab the ```docker-compose.yml``` [download](https://github.com/Scout064/event-inventory/blob/main/docker-compose.yml).

Put it to the path you setup in the ```prepare-docker.sh``` (Default: ```/srv/inventory```)

This ensures that we have the ability to monitor and update the Container Image.
This is needed if you want to use the "Update" Button in the Admin Panel.

##### Change the "docker-compose.yml" according to your needs
Choose your Image
```bash
  app:
    image: ghcr.io/scout064/event-inventory:[latest/version_tag]  # replace with the actual image you want
    container_name: inventory
```

Choose the Update Automation you want
```bash
# Uncomment ONE of the two Watchtower blocks below. (Comment out or delete the other)
# Option A: Automatic polling (checks every 24h, no other trigger needed)
# Option B: Manual trigger via Webinterface
```

##### Start Container
```bash
docker compose up -d
```

##### Web Setup
Visit ```<serverip>:8000/setup``` to configure the App


#### The "manual" Docker Way

##### Pull down Container Image
```bash
docker pull ghcr.io/scout064/event-inventory:[latest/version_tag]
```

##### Start Container
```bash
docker compose up -d
```

###### Web Setup
Visit ```http:<Server>:8000/setup```.
Here you can setup the App


### Option B — Manual

```bash
pip install -r requirements.txt
python wsgi.py
```

---

## 🔧 Configuration

Set environment variables:

```
DATABASE_URL=
SECRET_KEY=
```

---

## 🗄️ Database Setup

Initialize schema:

```bash
mysql -u user -p db < inventory_app/schema.sql
```

---

## 🧪 Testing

```bash
pytest
```

---

## 🚀 Deployment

* Docker image published via GitHub Actions
* Supports multi-arch (`amd64`, `arm64`)
* Uses OCI-compliant metadata & annotations

---

## 🔒 Security

* Authentication & session handling
* Input validation
* Dependency scanning via CI

---

## 📄 License

See [LICENSE](LICENSE) for details.

---

## 📬 Contact

[info@moessner-audio.de](mailto:info@moessner-audio.de)
