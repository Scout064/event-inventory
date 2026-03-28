# Event Inventory — Features & Roadmap

> **Legend**
>
> | Symbol | Meaning |
> |--------|---------|
> | 🔓 | Available without a license (login required) |
> | 🔑 | Requires a valid software license |
> | 🛡️ | Admin account required |
> | 🚧 | Planned — not yet implemented |

---

## Current Features

### Authentication & Session Management 🔓

- Username/password login with optional "Remember Me" persistent session
- Secure session cookies signed with a cryptographically generated `FLASK_SECRET_KEY`
- Automatic redirect to `/setup` if the application has not been initialised
- Logout from any page

---

### First-Run Setup Wizard 🔓

Available before any user exists — the only unauthenticated page in the app.

- Guided web-based setup wizard at `/setup`
- Configures database connection (host, port, name, user, password)
- Tests the database connection before writing anything to disk
- Creates the application database and app user via a root connection
- Applies base schema (`schema.sql`) and all migrations (`migrations.sql`) automatically
- Creates the admin account and an optional default user
- Uploads an optional company logo (PNG/JPEG)
- Sets the initial site name
- Hardens MariaDB after setup: randomises root password, removes anonymous users and test database
- Writes sensitive credentials to `.env` only — never to `config.json`

---

### Item Inventory 🔓

Core equipment catalogue, fully available without a license.

- Paginated item list (100 items per page)
- Full-text search across: Inventory ID, Name, Category, Serial Number, Manufacturer, Model, Description
- Create new items with a user-defined Inventory ID as primary key
- Edit item details (Inventory ID is locked after creation)
- Delete items (cascades to remove them from any productions)
- Autocomplete suggestions for Category, Manufacturer, and Model fields (populated from existing items)
- **CSV bulk import** — upload a CSV file to import multiple items at once
- **CSV template download** — pre-formatted template with headers and an example row
- Import result summary: imported / skipped (duplicate ID) / failed (missing fields)
- **QR code label generation** — per-item PNG label (100×54 mm, 300 DPI, Dymo LabelWriter compatible)
  - QR code encodes the Inventory ID
  - Optional company logo embedded in the QR code centre
  - Text fields auto-scale to fit label area
- **Full inventory PDF report** — all items sorted by name, downloadable

---

### Productions 🔓

Manage shows, events, or deployments and the equipment assigned to them.

- Searchable production list, sorted by date
- Create, edit, and delete productions (name, date, optional notes)
- Production detail page showing all assigned items
- Assign items to a production (live search via TomSelect widget)
- Remove individual items from a production
- Remove all items from a production at once (with confirmation)
- Batch remove: select multiple items with checkboxes and remove in one action
- **Bill of Materials (BOM) PDF** — production report including date, notes, and item table with serial numbers
- Sortable production table (click column headers to sort by ID, name, date, or notes)

---

### To-do Lists 🔑 *(License Required)*

Task management linked to productions.

- Standalone to-do list catalogue with search
- Create, edit, and delete to-do lists (title and optional description)
- Add tasks to a list with automatic append ordering
- Toggle individual tasks done/undone (checkbox, no page reload required)
- Delete individual tasks
- Task completion progress displayed as a counter (e.g. 3/7 done)
- **Attach to-do lists to productions** — a single list can be attached to multiple productions
- **Attach productions to to-do lists** — navigable from either side of the relationship
- Detach a list from a production without deleting either record
- Progress bar on the production view page showing completion status per attached list
- Link from production view directly to each to-do list

---

### Global Search 🔓

- Single search bar searches across all three entity types simultaneously:
  - Items (by name, Inventory ID, serial number, model)
  - Productions (by name, notes)
  - Users (by username)
- Results displayed in grouped sections on a single results page

---

### User Profile 🔓

Self-service profile management for all logged-in users.

- Update username, real name, email address, and birthday
- Change password (requires the current password to be entered first)
- Username validation: reserved names and admin-like usernames are blocked (with leet-speak normalisation)
- International character support in usernames (ä, ö, ü, é, ñ, etc.)
- Duplicate username/email detected and reported without crashing

---

### About & System Information 🔓 / 🛡️

- Current version and build date (read from `version.json`)
- Unique Instance ID display (used for license binding and server migration)
- Available stable release list (fetched from remote API, 1-hour cache)
- Recent beta/alpha release history
- Update availability notification when a newer stable version exists

**Admin only (🛡️):**
- Real-time server stats: CPU %, RAM usage, disk usage, database size
- System update trigger via Watchtower (streamed progress via Server-Sent Events)

---

### Admin Panel 🛡️

Accessible only to users with admin privileges.

#### User Management
- View all users
- Create new users (username, password, admin flag)
- Edit any user (username, password optional, admin flag)
- Delete users (cannot delete your own account)
- Password confirmation required on create/edit

#### Branding & Settings
- Update site name (displayed in the navbar, max 32 characters)
- Upload or replace company logo (PNG/JPEG)
- Remove the current logo
- Branding is applied globally across all pages and in QR code label generation

#### System Update
- Trigger a Docker image update via Watchtower HTTP API
- Live streamed update log in the browser (Server-Sent Events)
- Auto-detects server restart and reloads the UI when the container comes back online

---

### License Management 🛡️

Administration of the software license, accessible from the Admin panel.

- Enter and save license credentials (Client ID, Client Secret, License Key)
- All credentials encrypted with Fernet (AES-128-CBC) before database storage
- Immediate validation against the remote license API on save
- Manual force re-validation at any time
- License status displayed (Active / Invalid / No license configured)
- **License expiry warning banner** — shown to all users when fewer than 30 days remain until expiry
- Delete license and clear all cached state
- **License deactivation / server migration**:
  - Unbind the license from the current server via the remote API
  - Optionally pre-register the new server's Instance ID so activation requires no support ticket
- Instance ID displayed for easy copy/paste during migrations
- Local validation caching:
  - 24-hour remote API refresh cycle
  - Network failures fail-open (cached validity preserved during outages)

---

### Security & Infrastructure

- **HTTPS enforcement** — non-LAN requests on HTTP are redirected to HTTPS (CWE-601 safe: redirect built from configured domain, not user-supplied headers)
- **LAN exemption** — devices on 10.x, 192.168.x, 172.16–31.x, and 127.0.0.1 bypass HTTPS redirect
- **CSRF protection** on all forms (Flask-WTF)
- **Passwords hashed** with PBKDF2-HMAC-SHA256 (Werkzeug)
- **Encrypted license credentials** stored in database (Fernet)
- **Secret key rotation** — `FLASK_SECRET_KEY` auto-generated and persisted on first startup
- **Reserved username blocking** with leet-speak normalisation
- **Docker security hardening** (via `docker-compose.yml`):
  - AppArmor `runtime/default` profile
- **MariaDB hardening** during setup (root password randomised, anonymous users removed, test DB dropped)
- Automated dependency security review (Dependabot + GitHub Actions)

---

### Deployment & Operations

- Docker-based deployment with `docker-compose.yml`
- Automatic database backup on container startup (keeps last 2 backups)
- Schema and migration auto-apply on every startup (idempotent)
- Secret migration: moves credentials from `config.json` to `.env` if found on older installs
- `prepare-docker.sh` — one-command host setup including rootless Docker configuration
- Watchtower auto-update with label-based targeting
- Portainer included for container management UI
- Multiple update channels: `main` (Stable), `Beta`, `Alpha`

---

## Roadmap

The following features are planned for future releases. All roadmap items require a valid license.

---

### 🚧 Redesign Start Page 🔑

*Priority: High — next milestone*

The current dashboard (`/`) is a static placeholder. The planned redesign will turn it into an active, at-a-glance operations hub:

- Summary cards: total items, active productions, pending tasks, upcoming events
- Recent activity feed (latest item changes, production updates, completed tasks)
- Quick-action buttons for the most common workflows (add item, create production, new to-do)
- Upcoming productions widget (productions with dates in the next 30 days)
- License status and expiry indicator surfaced on the home page
- Responsive layout optimised for both desktop and tablet use in the field

---

### 🚧 Calendar 🔑

*Priority: High*

A visual calendar view for productions and scheduled events:

- Monthly, weekly, and day views
- Productions displayed as calendar entries on their scheduled date
- Click a calendar entry to navigate directly to the production detail page
- Create a production directly from the calendar by clicking a date
- Colour coding by production status or category
- Export calendar data to iCal format for use in external calendar apps

---

### 🚧 User Scheduling 🔑

*Priority: Medium*

Assign users to specific productions or shifts:

- Assign one or more users to a production
- Define roles per assignment (e.g. "Audio Engineer", "Stage Manager")
- View a user's scheduled productions from their profile
- Availability management: mark users as unavailable for date ranges
- Production detail page shows the assigned crew list
- Optional: email notification on assignment (requires SMTP configuration)

---

### 🚧 Chat Function 🔑

*Priority: Medium*

In-app messaging tied to productions and to-do lists:

- Per-production message thread visible to all assigned users
- Global team chat channel
- Message history persisted in the database
- Unread message indicator in the navbar
- Real-time delivery via WebSockets or Server-Sent Events (polling fallback)
- Admin moderation: delete messages
- Mention support (`@username`) with notification
- File attachment support (images, PDFs)

---

### 🛡️ Docker security hardening

*Priority: low*

- Read-only root filesystem on the app container
- `no-new-privileges` on all containers
- `cap_drop: ALL` with only minimum capabilities added back
- Rootless Docker support (`prepare-docker.sh`)
