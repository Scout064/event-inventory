import os
import re
import io
import csv
import psutil
from datetime import datetime
from functools import wraps

import mariadb
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file, abort,
    send_from_directory, jsonify
)
from flask_login import (
    LoginManager, login_user, logout_user, current_user,
    login_required, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Sub-module imports
from inventory_app.db import (
    load_config, save_config, get_db, init_db,
    get_item_suggestions, APP_DIR
)
from inventory_app.reports import (
    create_label_image, create_items_pdf, create_production_pdf
)
from inventory_app.forms import (
    SetupForm, LoginForm, ItemForm, ProductionForm,
    UserAdminForm, UserProfileForm
)
from inventory_app.version import (
    get_current_version, get_beta_releases, get_stable_releases
)

UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
QR_DIR = os.path.join(APP_DIR, "static", "qr_codes")
os.makedirs(QR_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

login_manager = LoginManager(app)
login_manager.login_view = "login"

LAN_REGEX = re.compile(
    r"^(127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+)$"
)

@app.before_request
def enforce_https():
    cfg = load_config()
    if not cfg.get("configured"):
        return
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    is_secure = request.is_secure or forwarded_proto == "https"
    remote_ip = request.remote_addr or ""
    if not is_secure and not LAN_REGEX.match(remote_ip):
        domain = cfg.get("app_domain")
        if not domain:
            abort(400, description="HTTPS enforcement failed: No trusted app_domain configured.")
        path = request.full_path
        secure_url = f"https://{domain}{path}"
        return redirect(secure_url, code=301)

class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin):
        self.id = str(id)
        self.username = username
        self.password_hash = password_hash
        self.is_admin = bool(is_admin)

def find_user_by_username(username):
    conn = get_db()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return User(*row) if row else None

def find_user_by_id(user_id):
    conn = get_db()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return User(*row) if row else None

@login_manager.user_loader
def load_user(user_id):
    cfg = load_config()
    if not cfg.get("configured"):
        return None
    return find_user_by_id(user_id)

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not getattr(current_user, "is_admin", False):
            flash("Admin access required.", "warning")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper

def save_logo(file):
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise ValueError("Invalid logo type")
    path = os.path.join(UPLOAD_DIR, "company_logo" + ext)
    file.save(path)
    return path

def create_users(cur, admin_data, default_data=None):
    cur.execute("SELECT id FROM users WHERE username=%s", (admin_data["username"],))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username,password_hash,is_admin) VALUES (%s,%s,%s)",
            (admin_data["username"], generate_password_hash(admin_data["password"]), True),
        )
    if default_data:
        cur.execute("SELECT id FROM users WHERE username=%s", (default_data["username"],))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username,password_hash,is_admin) VALUES (%s,%s,%s)",
                (default_data["username"], generate_password_hash(default_data["password"]), False),
            )

@app.context_processor
def inject_site_branding():
    cfg = load_config()
    site_cfg = {"site_name": cfg.get("site_name", "Inventory"), "logo_path": cfg.get("logo_path")}
    conn = get_db()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT setting_key, setting_value FROM settings")
            for row in cur.fetchall():
                site_cfg[row[0]] = row[1]
            cur.close()
        except Exception:
            pass
        finally:
            conn.close()
    return dict(site_cfg=site_cfg)

# --- Routes ---

@app.route("/setup", methods=["GET", "POST"])
def setup():
    cfg = load_config()
    if cfg.get("configured"):
        return redirect(url_for("index"))
    form = SetupForm()
    if form.validate_on_submit():
        logo_path = None
        file = form.company_logo.data
        if file and file.filename:
            try:
                logo_path = save_logo(file)
            except ValueError:
                flash("Logo must be PNG or JPEG.", "danger")
                return render_template("setup.html", form=form, configured=False)
        new_cfg = {
            "configured": True,
            "app_domain": form.app_domain.data.strip(),
            "db_host": form.db_host.data.strip(),
            "db_port": form.db_port.data.strip(),
            "db_name": form.db_name.data.strip(),
            "db_user": form.db_user.data.strip(),
            "db_pass": form.db_pass.data,
            "logo_path": logo_path,
        }
        try:
            with mariadb.connect(
                user=new_cfg["db_user"], password=new_cfg["db_pass"],
                host=new_cfg["db_host"], port=int(new_cfg["db_port"]),
                database=new_cfg["db_name"],
            ): pass
        except mariadb.Error as ex:
            flash(f"Database connection failed: {ex}", "danger")
            return render_template("setup.html", form=form, configured=False)
        
        save_config(new_cfg)
        init_db()
        conn = get_db()
        cur = conn.cursor()
        create_users(cur, 
            {"username": form.admin_username.data, "password": form.admin_password.data},
            {"username": form.default_user_username.data, "password": form.default_user_password.data} 
            if form.default_user_username.data else None
        )
        cur.execute("REPLACE INTO settings (setting_key, setting_value) VALUES ('site_name', 'Inventory')")
        if logo_path:
            cur.execute("REPLACE INTO settings (setting_key, setting_value) VALUES ('logo_path', %s)", (logo_path,))
        conn.commit()
        cur.close()
        conn.close()
        flash("Setup complete. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("setup.html", form=form, configured=False)

@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = load_config()
    if not cfg.get("configured"):
        return redirect(url_for("setup"))
    form = LoginForm()
    if form.validate_on_submit():
        user = find_user_by_username(form.username.data.strip())
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route('/items')
@login_required
def items():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    per_page = 100
    offset = (page - 1) * per_page
    conn = get_db()
    cur = conn.cursor()
    params = []
    where_clause = ""
    if q:
        where_clause = "WHERE inventory_id LIKE %s OR name LIKE %s OR category LIKE %s OR serial_number LIKE %s OR manufacturer LIKE %s OR model LIKE %s OR description LIKE %s"
        params = [f"%{q}%"] * 7
    
    cur.execute(f"SELECT COUNT(*) FROM items {where_clause}", tuple(params))
    total_items = cur.fetchone()[0]
    total_pages = (total_items + per_page - 1) // per_page
    
    cur.execute(f"SELECT inventory_id, name, category, serial_number, manufacturer, model FROM items {where_clause} ORDER BY inventory_id ASC LIMIT %s OFFSET %s", tuple(params + [per_page, offset]))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("items.html", rows=rows, page=page, total_pages=total_pages, total_items=total_items, q=q)

@app.route("/items/new", methods=["GET", "POST"])
@login_required
def items_new():
    form = ItemForm()
    if form.validate_on_submit():
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO items (inventory_id,name,category,description,serial_number,manufacturer,model) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (form.inventory_id.data.strip(), form.name.data.strip(), form.category.data.strip() if form.category.data else None,
                 form.description.data, form.serial_number.data.strip() if form.serial_number.data else None,
                 form.manufacturer.data.strip() if form.manufacturer.data else None, form.model.data.strip() if form.model.data else None))
            conn.commit()
            flash("Item created.", "success")
            return redirect(url_for("items"))
        except mariadb.Error as ex:
            flash(f"Error: {ex}", "danger")
        finally:
            cur.close()
            conn.close()
    return render_template("item_form.html", form=form, mode="new", suggestions=get_item_suggestions())

@app.route("/items/<inventory_id>/edit", methods=["GET", "POST"])
@login_required
def items_edit(inventory_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id,name,category,description,serial_number,manufacturer,model FROM items WHERE inventory_id=%s", (inventory_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)
    form = ItemForm(data={"inventory_id": row[0], "name": row[1], "category": row[2], "description": row[3], "serial_number": row[4], "manufacturer": row[5], "model": row[6]})
    if request.method == "POST" and form.validate_on_submit():
        try:
            cur.execute("UPDATE items SET name=%s, category=%s, description=%s, serial_number=%s, manufacturer=%s, model=%s WHERE inventory_id=%s",
                (form.name.data.strip(), form.category.data.strip() if form.category.data else None, form.description.data,
                 form.serial_number.data.strip() if form.serial_number.data else None, form.manufacturer.data.strip() if form.manufacturer.data else None,
                 form.model.data.strip() if form.model.data else None, inventory_id))
            conn.commit()
            flash("Item updated.", "success")
            return redirect(url_for("items"))
        except mariadb.Error as ex:
            flash(f"Error: {ex}", "danger")
    suggestions = get_item_suggestions()
    cur.close()
    conn.close()
    return render_template("item_form.html", form=form, mode="edit", suggestions=suggestions)

@app.route("/items/<inventory_id>/delete", methods=["POST"])
@login_required
def items_delete(inventory_id):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM items WHERE inventory_id=%s", (inventory_id,))
        conn.commit()
        flash("Item deleted.", "success")
    except mariadb.Error as ex:
        flash(f"Error: {ex}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("items"))

@app.route("/items/template")
@login_required
def items_download_template():
    bio = io.StringIO()
    writer = csv.writer(bio)
    writer.writerow(["inventory_id", "name", "category", "description", "serial_number", "manufacturer", "model"])
    writer.writerow(["MIC-001", "SM58", "Audio", "Dynamic vocal microphone", "SN123456", "Shure", "SM58-LC"])
    output = io.BytesIO(bio.getvalue().encode('utf-8'))
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="inventory_import_template.csv")

@app.route("/items/import", methods=["GET", "POST"])
@login_required
def items_import():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename.endswith('.csv'):
            flash("Please upload a valid CSV file.", "danger")
            return redirect(url_for("items"))
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        conn = get_db()
        cur = conn.cursor()
        success, dupe, error = 0, 0, 0
        for row in reader:
            cleaned = {k: (v.strip() if v else '') for k, v in row.items() if k}
            if not any(cleaned.values()): continue
            if not cleaned.get('inventory_id') or not cleaned.get('name'):
                error += 1; continue
            try:
                cur.execute("INSERT INTO items (inventory_id, name, category, description, serial_number, manufacturer, model) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (cleaned['inventory_id'], cleaned['name'], cleaned.get('category') or None, cleaned.get('description') or None, cleaned.get('serial_number') or None, cleaned.get('manufacturer') or None, cleaned.get('model') or None))
                success += 1
            except mariadb.IntegrityError as ie:
                if ie.errno == 1062: dupe += 1
                else: error += 1
            except Exception: error += 1
        conn.commit()
        cur.close()
        conn.close()
        flash(f"{success} Items Imported, {dupe} Duplicate IDs, {error} Errors.", "success" if error == 0 and dupe == 0 else "warning")
        return redirect(url_for("items"))
    return render_template("items_import.html")

@app.route("/items/search")
@login_required
def api_items_search():
    q = request.args.get("q", "").strip()
    if not q: return jsonify({"items": []})
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id, name FROM items WHERE inventory_id LIKE %s OR name LIKE %s LIMIT 50", (f"%{q}%", f"%{q}%"))
    items = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({"items": items})

@app.route("/productions")
@login_required
def productions():
    q = request.args.get("q", "").strip()
    conn = get_db()
    cur = conn.cursor()
    if q:
        cur.execute("SELECT id, name, date, notes FROM productions WHERE id LIKE %s OR name LIKE %s OR notes LIKE %s ORDER BY date DESC", (f"%{q}%", f"%{q}%", f"%{q}%"))
    else:
        cur.execute("SELECT id, name, date, notes FROM productions ORDER BY date DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("productions.html", rows=rows, q=q)

@app.route("/productions/new", methods=["GET", "POST"])
@login_required
def productions_new():
    form = ProductionForm()
    if form.validate_on_submit():
        date_val = None
        if form.date.data:
            try: date_val = datetime.strptime(form.date.data, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format, use YYYY-MM-DD", "warning")
                return render_template("production_form.html", form=form, mode="new")
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO productions (name,date,notes) VALUES (%s,%s,%s)", (form.name.data.strip(), date_val, form.notes.data))
            conn.commit()
            flash("Production created.", "success")
            return redirect(url_for("productions"))
        except mariadb.Error as ex: flash(f"Error: {ex}", "danger")
        finally:
            cur.close()
            conn.close()
    return render_template("production_form.html", form=form, mode="new")

@app.route("/productions/<int:pid>")
@login_required
def productions_view(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,name,date,notes FROM productions WHERE id=%s", (pid,))
    prod = cur.fetchone()
    if not prod:
        cur.close(); conn.close(); abort(404)
    cur.execute("SELECT i.inventory_id, i.name, i.category, i.serial_number, i.manufacturer, i.model FROM production_items pi JOIN items i ON i.inventory_id = pi.inventory_id WHERE pi.production_id=%s ORDER BY i.name", (pid,))
    items = cur.fetchall()
    cur.execute("SELECT inventory_id,name FROM items ORDER BY name")
    all_items = cur.fetchall()
    cur.close(); conn.close()
    return render_template("production_view.html", prod=prod, items=items, all_items=all_items)

@app.route("/labels/<inventory_id>.png")
@login_required
def label_png(inventory_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id, name, category, serial_number, manufacturer, model FROM items WHERE inventory_id=%s", (inventory_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row: abort(404)
    inventory_id_val, name, category, serial, manufacturer, model = (str(v or '') for v in row)
    bio = create_label_image(inventory_id_val, name, category, serial, manufacturer, model)
    return send_file(bio, mimetype="image/png", as_attachment=False, download_name=f"{inventory_id_val}.png")

@app.route("/reports/items.pdf")
@login_required
def report_items_pdf():
    bio = create_items_pdf()
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name="items_report.pdf")

@app.route("/reports/production/<int:pid>.pdf")
@login_required
def report_production_pdf(pid):
    result = create_production_pdf(pid)
    if not result: abort(404)
    bio, prod_name = result
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name=f"production_{pid}_BOM.pdf")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username, real_name, email, birthday, password_hash FROM users WHERE id=%s", (current_user.id,))
    row = cur.fetchone()
    if not row: cur.close(); conn.close(); abort(404)
    form = UserProfileForm()
    if request.method == "GET":
        form.username.data, form.real_name.data, form.email.data, form.birthday.data = row[0], row[1], row[2], row[3]
    if form.validate_on_submit():
        pw = form.password.data
        if pw and (not form.current_password.data or not check_password_hash(row[4], form.current_password.data)):
            flash("Current password incorrect.", "danger")
        else:
            try:
                new_hash = generate_password_hash(pw) if pw else row[4]
                cur.execute("UPDATE users SET username=%s, real_name=%s, email=%s, birthday=%s, password_hash=%s WHERE id=%s",
                    (form.username.data.strip(), form.real_name.data.strip(), form.email.data.strip(), form.birthday.data, new_hash, current_user.id))
                conn.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))
            except Exception as e: flash(f"Update failed: {e}", "danger")
    cur.close(); conn.close()
    return render_template("profile.html", form=form)

@app.route("/about")
@login_required
def about():
    stats = None
    if getattr(current_user, "is_admin", False):
        stats = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_total": round(psutil.virtual_memory().total / (1024 ** 3), 2),
            "disk_percent": psutil.disk_usage('/').percent,
            "disk_total": round(psutil.disk_usage('/').total / (1024 ** 3), 2),
            "db_size": "Unknown"
        }
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT SUM(data_length + index_length) / 1024 / 1024 FROM information_schema.tables WHERE table_schema = DATABASE()")
                size = cur.fetchone()[0]
                if size: stats["db_size"] = f"{round(size, 2)} MB"
                cur.close()
            finally: conn.close()
    return render_template("about.html", currentVersion=get_current_version(), releases=get_stable_releases(), beta=get_beta_releases(5), stats=stats)

@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        site_name = request.form.get("site_name", "Inventory").strip()
        cur.execute("REPLACE INTO settings (setting_key, setting_value) VALUES ('site_name', %s)", (site_name,))
        if request.form.get("remove_logo") == "yes":
            cur.execute("REPLACE INTO settings (setting_key, setting_value) VALUES ('logo_path', NULL)")
        else:
            file = request.files.get("company_logo")
            if file and file.filename:
                try:
                    path = save_logo(file)
                    cur.execute("REPLACE INTO settings (setting_key, setting_value) VALUES ('logo_path', %s)", (path,))
                except ValueError: flash("Invalid file type.", "danger")
        conn.commit()
        flash("Branding updated.", "success")
        return redirect(url_for("admin_settings"))
    cur.execute("SELECT setting_key, setting_value FROM settings")
    cfg = {r[0]: r[1] for r in cur.fetchall()}
    cur.close(); conn.close()
    return render_template("admin_settings.html", cfg=cfg)

@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin FROM users ORDER BY username")
    users = cur.fetchall()
    cur.close(); conn.close()
    return render_template("admin_users.html", users=users)

@app.route("/admin/users/new", methods=["GET", "POST"])
@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_user_edit(user_id=None):
    conn = get_db()
    cur = conn.cursor()
    user_to_edit = None
    if user_id:
        cur.execute("SELECT id, username, is_admin FROM users WHERE id=%s", (user_id,))
        user_to_edit = cur.fetchone()
        if not user_to_edit: abort(404)
    form = UserAdminForm()
    if request.method == "GET" and user_to_edit:
        form.username.data, form.is_admin.data = user_to_edit[1], bool(user_to_edit[2])
    if form.validate_on_submit():
        uname, is_admin, pw = form.username.data.strip(), 1 if form.is_admin.data else 0, form.password.data
        try:
            if user_id:
                if pw: cur.execute("UPDATE users SET username=%s, password_hash=%s, is_admin=%s WHERE id=%s", (uname, generate_password_hash(pw), is_admin, user_id))
                else: cur.execute("UPDATE users SET username=%s, is_admin=%s WHERE id=%s", (uname, is_admin, user_id))
            else:
                if not pw: flash("Password required for new users.", "danger"); return render_template("user_form.html", form=form, mode="new")
                cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)", (uname, generate_password_hash(pw), is_admin))
            conn.commit()
            flash("User saved.", "success")
            return redirect(url_for("admin_users"))
        except Exception as e: flash(f"Error: {e}", "danger")
    return render_template("user_form.html", form=form, mode="edit" if user_id else "new")

@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_user_delete(user_id):
    if str(user_id) == str(current_user.id):
        flash("You cannot delete yourself.", "danger")
        return redirect(url_for("admin_users"))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        flash("User deleted.", "success")
    finally: cur.close(); conn.close()
    return redirect(url_for("admin_users"))

@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory('uploads', filename)

def create_app():
    cfg = load_config()
    if cfg.get("configured"):
        try: init_db()
        except Exception as e: print(f"ERROR: DB failed: {e}")
    return app

application = create_app()
if __name__ == "__main__":
    application.run(host="0.0.0.0", port=8000, debug=False)
