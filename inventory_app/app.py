import os
import json
import re
import io
import mariadb
import qrcode
import csv
from functools import wraps
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, abort, send_from_directory, jsonify
)
from flask_login import (
    LoginManager, login_user, logout_user,
    current_user, login_required, UserMixin
)
from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SubmitField, BooleanField,
    TextAreaField, FileField, DateField
)
from wtforms.validators import (
    DataRequired, Length, Optional, Email,
    EqualTo, Regexp
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from inventory_app.security import ReservedUsername


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
QR_DIR = os.path.join(APP_DIR, "static", "qr_codes")
os.makedirs(QR_DIR, exist_ok=True)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"configured": False}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


def get_db():
    cfg = load_config()
    if not cfg.get("configured"):
        return None
    conn = mariadb.connect(
        user=cfg["db_user"],
        password=cfg["db_pass"],
        host=cfg["db_host"],
        port=int(cfg.get("db_port", 3306)),
        database=cfg["db_name"],
    )
    return conn


def init_db():
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    schema_path = os.path.join(APP_DIR, "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            # Split by semicolon to get individual commands
            sql_commands = f.read().split(';')
        for command in sql_commands:
            if command.strip():
                try:
                    cur.execute(command)
                except mariadb.Error as e:
                    print(f"Error executing command: {e}")
        conn.commit()
        print("Database initialized from schema.sql")
    else:
        print("schema.sql not found. Skipping initialization.")
    cur.close()
    conn.close()


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
        domain = cfg.get("app_domain", request.host)
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
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username=%s",
        (username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return User(*row)
    return None


def find_user_by_id(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE id=%s",
        (user_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return User(*row)
    return None


@login_manager.user_loader
def load_user(user_id):
    cfg = load_config()
    if not cfg.get("configured"):
        return None
    return find_user_by_id(user_id)


class SetupForm(FlaskForm):
    app_domain = StringField(
        "App Domain (e.g., inventory.example.com)",
        validators=[DataRequired()],
        default="localhost:8000"
    )
    db_host = StringField("DB Host", validators=[DataRequired()], default="localhost")
    db_port = StringField("DB Port", validators=[DataRequired()], default="3306")
    db_name = StringField(
        "DB Name", validators=[DataRequired()], default="inventory_db"
    )
    db_user = StringField("DB User", validators=[DataRequired()], default="inventory_user")
    db_pass = PasswordField("DB Password", validators=[DataRequired()])
    admin_username = StringField(
        "Admin Username", validators=[DataRequired(), Length(min=3, max=128)], default="admin"
    )
    admin_password = PasswordField(
        "Admin Password", validators=[DataRequired(), Length(min=6)]
    )
    default_user_username = StringField(
        "Default User Username", validators=[Optional(), Length(min=3, max=128)]
    )
    default_user_password = PasswordField(
        "Default User Password", validators=[Optional(), Length(min=6)]
    )
    company_logo = FileField("Company Logo (PNG/JPEG)")
    submit = SubmitField("Initialize")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")


class ItemForm(FlaskForm):
    inventory_id = StringField(
        "Inventory ID",
        validators=[
            DataRequired(message="ID is required and cannot be blank"),
            Length(min=1, max=32)
        ]
    )
    name = StringField(
        "Name",
        validators=[
            DataRequired(message="Name is required and cannot be blank"),
            Length(min=1, max=120)
        ]
    )
    category = StringField("Category", validators=[Optional(), Length(max=50)])
    description = TextAreaField("Description", validators=[Optional(), Length(max=250)])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=50)])
    manufacturer = StringField("Manufacturer", validators=[Optional(), Length(max=50)])
    model = StringField("Model", validators=[Optional(), Length(max=50)])
    submit = SubmitField("Save")


class ProductionForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            DataRequired(message="Production name is required"),
            Length(min=1, max=32, message="Name must be between 1 and 32 characters")
        ]
    )
    date = StringField("Date (YYYY-MM-DD)", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=255, message="Notes cannot exceed 255 characters")])
    submit = SubmitField("Save")


class UserAdminForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=32, message="Username must be between 3 and 32 characters."),
            # Allows letters, numbers, specific language characters, dots, hyphens, and underscores
            Regexp(r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ._\-]+$', message="Username contains invalid special characters.")
        ]
    )
    password = PasswordField("Password (leave blank to keep current)", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[EqualTo('password', message='Passwords must match')])
    is_admin = BooleanField("Grant Admin Privileges")
    submit = SubmitField("Save User")


class UserProfileForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=32, message="Username must be between 3 and 32 characters."),
            Regexp(
                r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ._\-]+$',
                message="Username contains invalid special characters."
            ),
            ReservedUsername()
        ]
    )
    real_name = StringField(
        "Real Name",
        validators=[
            Optional(),
            Length(max=32, message="Real name cannot exceed 32 characters."),
            # Same as above but allows spaces
            Regexp(
                r'^[a-zA-Z0-9äöüÄÖÜßéèêáàâíìîóòôúùûñÑçÇ\s.\-]+$',
                message="Real name contains invalid special characters."
            )
        ]
    )
    email = StringField(
        "E-Mail Address",
        validators=[
            Optional(),
            Email(),
            Length(max=32, message="Email cannot exceed 32 characters.")
        ]
    )
    birthday = DateField("Birthday", format='%Y-%m-%d', validators=[Optional()])
    password = PasswordField("New Password (leave blank to keep current)", validators=[Optional(), Length(min=6)])
    confirm_password = PasswordField("Confirm New Password", validators=[EqualTo('password', message='Passwords must match')])
    submit = SubmitField("Save Profile")


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
        cur.execute(
            "SELECT id FROM users WHERE username=%s", (default_data["username"],)
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO users (username,password_hash,is_admin) VALUES (%s,%s,%s)",
                (
                    default_data["username"],
                    generate_password_hash(default_data["password"]),
                    False,
                ),
            )


@app.context_processor
def inject_site_branding():
    cfg = load_config()
    return dict(site_cfg=cfg)


# --- Routes --- #

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
                user=new_cfg["db_user"],
                password=new_cfg["db_pass"],
                host=new_cfg["db_host"],
                port=int(new_cfg["db_port"]),
                database=new_cfg["db_name"],
            ):
                pass
        except mariadb.Error as ex:
            flash(f"Database connection failed: {ex}", "danger")
            return render_template("setup.html", form=form, configured=False)
        save_config(new_cfg)
        init_db()
        conn = get_db()
        cur = conn.cursor()
        create_users(
            cur,
            {"username": form.admin_username.data, "password": form.admin_password.data},
            {"username": form.default_user_username.data, "password": form.default_user_password.data}
            if form.default_user_username.data and form.default_user_password.data
            else None
        )
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


# Items
@app.route('/items')
@login_required
def items():
    # 1. Get parameters from the URL
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '').strip()
    per_page = 100
    offset = (page - 1) * per_page
    conn = get_db()
    cur = conn.cursor()
    # 2. Build the search condition
    search_wildcard = f"%{q}%"
    where_clause = ""
    params = []
    if q:
        where_clause = """
            WHERE inventory_id LIKE %s
               OR name LIKE %s
               OR category LIKE %s
               OR serial_number LIKE %s
               OR manufacturer LIKE %s
               OR model LIKE %s
               OR description LIKE %s
        """
        params = [search_wildcard] * 7
    # 3. Get total count for this search (for pagination)
    cur.execute(f"SELECT COUNT(*) FROM items {where_clause}", tuple(params))
    total_items = cur.fetchone()[0]
    total_pages = (total_items + per_page - 1) // per_page
    # 4. Fetch the specific page of data
    # We order by inventory_id to ensure a stable sequence across pages
    query = f"""
        SELECT inventory_id, name, category, serial_number, manufacturer, model
        FROM items
        {where_clause}
        ORDER BY inventory_id ASC
        LIMIT %s OFFSET %s
    """
    cur.execute(query, tuple(params + [per_page, offset]))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "items.html",
        rows=rows,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        q=q
    )


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def items_new():
    form = ItemForm()
    if form.validate_on_submit():
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO items (inventory_id,name,category,description,serial_number,manufacturer,model)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (form.inventory_id.data.strip(), form.name.data.strip(),
                         form.category.data.strip() if form.category.data else None,
                         form.description.data, form.serial_number.data.strip() if form.serial_number.data else None,
                         form.manufacturer.data.strip() if form.manufacturer.data else None,
                         form.model.data.strip() if form.model.data else None))
            conn.commit()
            flash("Item created.", "success")
            return redirect(url_for("items"))
        except mariadb.Error as ex:
            conn.rollback()
            flash(f"Error: {ex}", "danger")
        finally:
            cur.close()
            conn.close()
    return render_template("item_form.html", form=form, mode="new")


@app.route("/items/<inventory_id>/edit", methods=["GET", "POST"])
@login_required
def items_edit(inventory_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT inventory_id,name,category,description,serial_number,
                   manufacturer,model FROM items WHERE inventory_id=%s""", (inventory_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)

    form = ItemForm(data={
        "inventory_id": row[0],
        "name": row[1],
        "category": row[2],
        "description": row[3],
        "serial_number": row[4],
        "manufacturer": row[5],
        "model": row[6],
    })
    if request.method == "POST" and form.validate_on_submit():
        try:
            # Update DB
            cur.execute("""UPDATE items SET name=%s, category=%s, description=%s, serial_number=%s,
                           manufacturer=%s, model=%s WHERE inventory_id=%s""",
                        (form.name.data.strip(),
                         form.category.data.strip() if form.category.data else None,
                         form.description.data,
                         form.serial_number.data.strip() if form.serial_number.data else None,
                         form.manufacturer.data.strip() if form.manufacturer.data else None,
                         form.model.data.strip() if form.model.data else None,
                         inventory_id))
            conn.commit()
            flash("Item updated.", "success")
            return redirect(url_for("items"))
        except mariadb.Error as ex:
            conn.rollback()
            flash(f"Error: {ex}", "danger")
    cur.close()
    conn.close()
    return render_template("item_form.html", form=form, mode="edit")


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
        conn.rollback()
        flash(f"Error: {ex}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("items"))


@app.route("/items/template")
@login_required
def items_download_template():
    """Generates and serves a blank CSV template for bulk import."""
    bio = io.StringIO()
    writer = csv.writer(bio)
    # Headers based on ItemForm and DB schema
    writer.writerow([
        "inventory_id", "name", "category", "description",
        "serial_number", "manufacturer", "model"
    ])
    # Add an example row for the user
    writer.writerow([
        "MIC-001", "SM58", "Audio", "Dynamic vocal microphone",
        "SN123456", "Shure", "SM58-LC"
    ])
    output = io.BytesIO()
    output.write(bio.getvalue().encode('utf-8'))
    output.seek(0)
    return send_file(
        output,
        mimetype="text/csv",
        as_attachment=True,
        download_name="inventory_import_template.csv"
    )


def process_item_row(cur, row):
    """
    Helper to process a single CSV row.
    Returns: 0 (Skip Empty), 1 (Success), 2 (Duplicate), 3 (Error)
    """
    # Clean the row to handle None values and strip whitespace safely
    cleaned = {k: (v.strip() if v else '') for k, v in row.items() if k}
    # If the row is completely empty (e.g., trailing commas), silently skip it
    if not any(cleaned.values()):
        return 0
    inv_id = cleaned.get('inventory_id', '')
    name = cleaned.get('name', '')
    # Enforce mandatory fields: ID and Name cannot be blank
    if not inv_id or not name:
        return 3
    try:
        cur.execute("""
            INSERT INTO items (inventory_id, name, category, description,
                               serial_number, manufacturer, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            inv_id,
            name,
            cleaned.get('category') or None,
            cleaned.get('description') or None,
            cleaned.get('serial_number') or None,
            cleaned.get('manufacturer') or None,
            cleaned.get('model') or None
        ))
        return 1  # Success
    except mariadb.IntegrityError as ie:
        if ie.errno == 1062:
            return 2  # Duplicate
        return 3      # Other DB Error
    except Exception as e:
        print(f"Row Exception: {e}")
        return 3      # General Error


@app.route("/items/import", methods=["GET", "POST"])
@login_required
def items_import():
    """Handles the uploading and processing of the bulk import CSV."""
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or not file.filename.endswith('.csv'):
            flash("Please upload a valid CSV file.", "danger")
            return redirect(url_for("items"))
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        conn = get_db()
        cur = conn.cursor()
        counts = {1: 0, 2: 0, 3: 0}  # 1: Success, 2: Duplicate, 3: Error
        for row in reader:
            result = process_item_row(cur, row)
            if result in counts:  # Result 0 (Skip) is ignored and not counted
                counts[result] += 1
        conn.commit()
        cur.close()
        conn.close()
        msg = f"{counts[1]} Items Imported, {counts[2]} not Imported (identical ID)"
        if counts[3] > 0:
            msg += f". Warning: {counts[3]} rows had missing mandatory fields or errors."
        flash(msg, "success" if counts[2] == 0 and counts[3] == 0 else "warning")
        return redirect(url_for("items"))
    return render_template("items_import.html")


@app.route("/items/search")
@login_required
def api_items_search():
    """Server-side search for the TomSelect dropdown."""
    q = request.args.get("q", "").strip()
    # If the search query is empty, return an empty list
    if not q:
        return jsonify({"items": []})
    conn = get_db()
    cur = conn.cursor()
    try:
        # Search by ID or Name, limit to 50 so the frontend stays snappy
        query = """
            SELECT inventory_id, name
            FROM items
            WHERE inventory_id LIKE %s OR name LIKE %s
            LIMIT 50
        """
        search_term = f"%{q}%"
        cur.execute(query, (search_term, search_term))
        results = cur.fetchall()
        # Format the results as a list of dictionaries for JSON serialization
        items = [{"id": r[0], "name": r[1]} for r in results]
        return jsonify({"items": items})
    except mariadb.Error as e:
        print(f"Database error during search: {e}")
        return jsonify({"items": []}), 500
    finally:
        cur.close()
        conn.close()


# Productions
@app.route("/productions")
@login_required
def productions():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,name,date,notes FROM productions ORDER BY date DESC, name ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("productions.html", rows=rows)


@app.route("/productions/new", methods=["GET", "POST"])
@login_required
def productions_new():
    form = ProductionForm()
    if form.validate_on_submit():
        date_val = None
        if form.date.data:
            try:
                date_val = datetime.strptime(form.date.data, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format, use YYYY-MM-DD", "warning")
                return render_template("production_form.html", form=form, mode="new")
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO productions (name,date,notes) VALUES (%s,%s,%s)",
                        (form.name.data.strip(), date_val, form.notes.data))
            conn.commit()
            flash("Production created.", "success")
            return redirect(url_for("productions"))
        except mariadb.Error as ex:
            conn.rollback()
            flash(f"Error: {ex}", "danger")
        finally:
            cur.close()
            conn.close()
    return render_template("production_form.html", form=form, mode="new")


@app.route("/productions/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def productions_edit(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,name,date,notes FROM productions WHERE id=%s", (pid,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)
    form = ProductionForm(data={
        "name": row[1],
        "date": row[2].strftime("%Y-%m-%d") if row[2] else "",
        "notes": row[3]
    })
    if request.method == "POST" and form.validate_on_submit():
        date_val = None
        if form.date.data:
            try:
                date_val = datetime.strptime(form.date.data, "%Y-%m-%d").date()
            except ValueError:
                flash("Invalid date format, use YYYY-MM-DD", "warning")
                return render_template("production_form.html", form=form, mode="edit")
        try:
            cur.execute("UPDATE productions SET name=%s, date=%s, notes=%s WHERE id=%s",
                        (form.name.data.strip(), date_val, form.notes.data, pid))
            conn.commit()
            flash("Production updated.", "success")
            return redirect(url_for("productions"))
        except mariadb.Error as ex:
            conn.rollback()
            flash(f"Error: {ex}", "danger")
    cur.close()
    conn.close()
    return render_template("production_form.html", form=form, mode="edit")


@app.route("/productions/<int:pid>/delete", methods=["POST"])
@login_required
def productions_delete(pid):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM productions WHERE id=%s", (pid,))
        conn.commit()
        flash("Production deleted.", "success")
    except mariadb.Error as ex:
        conn.rollback()
        flash(f"Error: {ex}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("productions"))


@app.route("/productions/<int:pid>")
@login_required
def productions_view(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,name,date,notes FROM productions WHERE id=%s", (pid,))
    prod = cur.fetchone()
    if not prod:
        cur.close()
        conn.close()
        abort(404)
    cur.execute("""SELECT i.inventory_id, i.name, i.category, i.serial_number, i.manufacturer, i.model
                   FROM production_items pi
                   JOIN items i ON i.inventory_id = pi.inventory_id
                   WHERE pi.production_id=%s
                   ORDER BY i.name""", (pid,))
    items = cur.fetchall()
    # All items for assignment
    cur.execute("SELECT inventory_id,name FROM items ORDER BY name")
    all_items = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("production_view.html", prod=prod, items=items, all_items=all_items)


@app.route("/productions/<int:pid>/assign", methods=["POST"])
@login_required
def productions_assign(pid):
    inventory_id = request.form.get("inventory_id", "").strip()
    if not inventory_id:
        flash("Select an item.", "warning")
        return redirect(url_for("productions_view", pid=pid))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT IGNORE INTO production_items (production_id, inventory_id) VALUES (%s,%s)",
                    (pid, inventory_id))
        conn.commit()
        flash("Item assigned.", "success")
    except mariadb.Error as ex:
        conn.rollback()
        flash(f"Error: {ex}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("productions_view", pid=pid))


@app.route("/productions/<int:pid>/remove", methods=["POST"])
@login_required
def productions_remove(pid):
    inventory_id = request.form.get("inventory_id", "").strip()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM production_items WHERE production_id=%s AND inventory_id=%s", (pid, inventory_id))
        conn.commit()
        flash("Item removed.", "success")
    except mariadb.Error as ex:
        conn.rollback()
        flash(f"Error: {ex}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("productions_view", pid=pid))


@app.route("/productions/<int:pid>/clear", methods=["POST"])
@login_required
def productions_clear_all(pid):
    """Removes every item assigned to a specific production."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM production_items WHERE production_id = %s", (pid,))
        conn.commit()
        flash("All items removed from production.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error clearing items: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("productions_view", pid=pid))


@app.route("/productions/<int:pid>/batch_remove", methods=["POST"])
@login_required
def productions_batch_remove(pid):
    """Removes a list of selected items from the production."""
    item_ids = request.form.getlist("item_ids")
    if not item_ids:
        flash("No items were selected for removal.", "warning")
        return redirect(url_for("productions_view", pid=pid))
    conn = get_db()
    cur = conn.cursor()
    try:
        # Construct a query like: DELETE ... WHERE pid = %s AND inventory_id IN (%s, %s, %s)
        format_strings = ','.join(['%s'] * len(item_ids))
        query = f"DELETE FROM production_items WHERE production_id = %s AND inventory_id IN ({format_strings})"
        cur.execute(query, [pid] + item_ids)
        conn.commit()
        flash(f"Successfully removed {len(item_ids)} items.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error during batch removal: {e}", "danger")
    finally:
        cur.close()
        conn.close()
    return redirect(url_for("productions_view", pid=pid))


# QR label with logo in center
def generate_qr_with_logo(data_text, logo_path=None, box_size=10, border=4):
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border
    )
    qr.add_data(data_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    if logo_path and os.path.exists(logo_path):
        logo = Image.open(logo_path).convert("RGBA")
        # Scale logo to ~22% of QR size
        qr_w, qr_h = img.size
        logo_size = int(min(qr_w, qr_h) * 0.22)
        logo.thumbnail((logo_size, logo_size), Image.LANCZOS)
        lx = (qr_w - logo.size[0]) // 2
        ly = (qr_h - logo.size[1]) // 2
        img.paste(logo, (lx, ly), logo)

    return img


@app.route("/labels/<inventory_id>.png")
@login_required
def label_png(inventory_id):
    cfg = load_config()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT inventory_id, name, category, serial_number, manufacturer, model
        FROM items
        WHERE inventory_id=%s
    """, (inventory_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404)
    # Unpack values and replace None with empty strings
    inventory_id_val, name, category, serial, manufacturer, model = (str(v or '') for v in row)
    # Generate QR
    qr = generate_qr_with_logo(inventory_id_val, cfg.get("logo_path"))
    # Create label image (100mm x 54mm at 300dpi)
    dpi = 300
    width_px = int((100 / 25.4) * dpi)
    height_px = int((54 / 25.4) * dpi)
    label = Image.new("RGB", (width_px, height_px), "white")
    # Paste QR on the left
    qr_size = int(height_px * 0.9)
    qr = qr.resize((qr_size, qr_size), Image.LANCZOS)
    label.paste(qr, (int(height_px * 0.05), int(height_px * 0.05)))
    draw = ImageDraw.Draw(label)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    # Prepare text lines
    lines = []
    if inventory_id_val:
        lines.append(inventory_id_val)
    if name or category:
        lines.append(f"{name} ({category})" if category else name)
    if serial:
        lines.append(f"SN: {serial}")
    if manufacturer or model:
        lines.append(f"{manufacturer} {model}".strip())
    # Text area
    x = qr_size + int(height_px * 0.1)
    y_start = int(height_px * 0.12)
    max_text_width = width_px - x - int(height_px * 0.05)
    max_text_height = height_px - y_start - int(height_px * 0.05)
    # Initial sizes
    base_font_size = int(height_px * 0.08)
    min_font_size = 10
    # Function to compute block height for given font size

    def compute_block_height(f_size):
        return len(lines) * f_size + (len(lines) - 1) * int(f_size * 0.5)
    # Scale font size down if block is too tall
    font_size = base_font_size
    while compute_block_height(font_size) > max_text_height and font_size > min_font_size:
        font_size -= 1
    # Now draw each line, adjusting horizontally too
    y = y_start
    for idx, text in enumerate(lines):
        size = font_size
        font = ImageFont.truetype(font_path, size)
        # Shrink font horizontally if too wide
        while draw.textlength(text, font=font) > max_text_width and size > min_font_size:
            size -= 1
            font = ImageFont.truetype(font_path, size)
        draw.text((x, y), text, font=font, fill="black")
        y += size + int(size * 0.5)

    # Output PNG
    bio = io.BytesIO()
    label.save(bio, format="PNG")
    bio.seek(0)
    return send_file(bio, mimetype="image/png", as_attachment=False, download_name=f"{inventory_id_val}.png")


# PDF reports
@app.route("/reports/items.pdf")
@login_required
def report_items_pdf():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""SELECT inventory_id, name, category, serial_number, manufacturer, model
                   FROM items ORDER BY name""")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4, pageCompression=1)
    width, height = A4
    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, "Item Inventory Report")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    for r in rows:
        line = f"{r[0]} | {r[1]} | {r[2] or ''} | SN:{r[3] or ''} | {r[4] or ''} {r[5] or ''}"
        if y < 20 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("Helvetica", 10)
        c.drawString(15 * mm, y, line[:120])
        y -= 6 * mm
    c.showPage()
    c.save()
    bio.seek(0)
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name="items_report.pdf")


@app.route("/reports/production/<int:pid>.pdf")
@login_required
def report_production_pdf(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,name,date,notes FROM productions WHERE id=%s", (pid,))
    prod = cur.fetchone()
    if not prod:
        cur.close()
        conn.close()
        abort(404)
    cur.execute("""SELECT i.inventory_id, i.name, i.category, i.serial_number, i.manufacturer, i.model
                   FROM production_items pi
                   JOIN items i ON i.inventory_id = pi.inventory_id
                   WHERE pi.production_id=%s
                   ORDER BY i.name""", (pid,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4, pageCompression=1)
    width, height = A4
    y = height - 20 * mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, y, f"BOM – {prod[1]}")
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, y, f"Date: {prod[2] or ''}")
    y -= 6 * mm
    if prod[3]:
        c.drawString(20 * mm, y, f"Notes: {prod[3][:90]}")
        y -= 8 * mm
    c.setFont("Helvetica", 10)
    for r in items:
        if y < 20 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("Helvetica", 10)
        line = f"{r[0]} | {r[1]} | {r[2] or ''} | SN:{r[3] or ''} | {r[4] or ''} {r[5] or ''}"
        c.drawString(15 * mm, y, line[:120])
        y -= 6 * mm
    c.showPage()
    c.save()
    bio.seek(0)
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name=f"production_{pid}_BOM.pdf")


@app.route("/search")
@login_required
def search():
    query = request.args.get("q", "").strip()

    if not query:
        return redirect(url_for("index"))

    search_term = f"%{query}%"
    conn = get_db()
    if not conn:
        flash("Database connection error.", "danger")
        return redirect(url_for("index"))

    cur = conn.cursor()
    # 1. Search Items (Matched with your schema)
    cur.execute("""
        SELECT inventory_id, name, category, manufacturer
        FROM items
        WHERE name LIKE %s OR inventory_id LIKE %s OR serial_number LIKE %s OR model LIKE %s
    """, (search_term, search_term, search_term, search_term))
    items_list = cur.fetchall()
    # 2. Search Productions
    cur.execute("""
        SELECT id, name, date
        FROM productions
        WHERE name LIKE %s OR notes LIKE %s
    """, (search_term, search_term))
    productions_list = cur.fetchall()
    # 3. Search Users
    cur.execute("SELECT id, username, is_admin FROM users WHERE username LIKE %s", (search_term,))
    users_list = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "search_results.html",
        query=query,
        items=items_list,
        productions=productions_list,
        users=users_list
    )


# User Profile Route
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db()
    cur = conn.cursor()
    # Fetch current user's full data
    cur.execute("SELECT username, real_name, email, birthday FROM users WHERE id=%s", (current_user.id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)
    form = UserProfileForm()
    # Pre-fill the form on GET request
    if request.method == "GET":
        form.username.data = row[0]
        form.real_name.data = row[1]
        form.email.data = row[2]
        form.birthday.data = row[3]  # WTForms DateField handles the datetime.date object automatically
    if form.validate_on_submit():
        uname = form.username.data.strip()
        rname = form.real_name.data.strip() if form.real_name.data else None
        email = form.email.data.strip() if form.email.data else None
        bday = form.birthday.data
        pw = form.password.data
        try:
            if pw:
                # Update including new password
                cur.execute("""UPDATE users
                               SET username=%s, real_name=%s, email=%s, birthday=%s, password_hash=%s
                               WHERE id=%s""",
                            (uname, rname, email, bday, generate_password_hash(pw), current_user.id))
            else:
                # Update without changing password
                cur.execute("""UPDATE users
                               SET username=%s, real_name=%s, email=%s, birthday=%s
                               WHERE id=%s""",
                            (uname, rname, email, bday, current_user.id))
            conn.commit()
            # Keep the flask-login session in sync if they changed their username
            current_user.username = uname
            flash("Profile updated successfully.", "success")
            return redirect(url_for("profile"))
        except mariadb.Error as e:
            conn.rollback()
            # Handle duplicate username or email gracefully
            if "Duplicate entry" in str(e):
                flash("That Username or E-Mail is already in use by another account.", "danger")
            else:
                flash(f"Database Error: {e}", "danger")
    cur.close()
    conn.close()
    return render_template("profile.html", form=form)


# Admin-only routes

@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
@admin_required
def admin_settings():
    cfg = load_config()
    if request.method == "POST":
        cfg["site_name"] = request.form.get("site_name", "Event Inventory").strip()
        if request.form.get("remove_logo"):
            cfg["logo_path"] = None
        else:
            file = request.files.get("company_logo")
            if file and file.filename:
                filename = secure_filename(file.filename)
                ext = os.path.splitext(filename)[1].lower()
                if ext in [".png", ".jpg", ".jpeg"]:
                    logo_path = os.path.join(UPLOAD_DIR, "company_logo" + ext)
                    file.save(logo_path)
                    cfg["logo_path"] = logo_path
        save_config(cfg)
        flash("Branding updated.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", cfg=cfg)


@app.route("/admin/users")
@login_required
@admin_required
def admin_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin FROM users ORDER BY username")
    users = cur.fetchall()
    cur.close()
    conn.close()
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
        if not user_to_edit:
            abort(404)

    form = UserAdminForm()

    # Pre-fill if editing
    if request.method == "GET" and user_to_edit:
        form.username.data = user_to_edit[1]
        form.is_admin.data = bool(user_to_edit[2])

    if form.validate_on_submit():
        uname = form.username.data.strip()
        is_admin = 1 if form.is_admin.data else 0
        pw = form.password.data

        try:
            if user_id:
                if pw:
                    cur.execute("UPDATE users SET username=%s, password_hash=%s, is_admin=%s WHERE id=%s",
                                (uname, generate_password_hash(pw), is_admin, user_id))
                else:
                    cur.execute("UPDATE users SET username=%s, is_admin=%s WHERE id=%s",
                                (uname, is_admin, user_id))
                flash("User updated.", "success")
            else:
                if not pw:
                    flash("Password is required for new users.", "danger")
                    return render_template("user_form.html", form=form, mode="new")
                cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)",
                            (uname, generate_password_hash(pw), is_admin))
                flash("User created.", "success")

            conn.commit()
            return redirect(url_for("admin_users"))
        except mariadb.Error as e:
            flash(f"Error: {e}", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template("user_form.html", form=form, mode="edit" if user_id else "new")


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_user_delete(user_id):
    # Prevent the admin from deleting themselves
    if str(user_id) == str(current_user.id):
        flash("You cannot delete your own admin account.", "danger")
        return redirect(url_for("admin_users"))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        flash("User deleted successfully.", "success")
    except mariadb.Error as e:
        conn.rollback()
        flash(f"Error deleting user: {e}", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for("admin_users"))


# Optional static serving
@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory('uploads', filename)


# --- Integrated Entry Point --- #

def create_app():
    """
    Initializes the application logic.
    This runs both in production (WSGI) and development (Manual).
    """
    cfg = load_config()
    if not cfg.get("configured"):
        # This prints to console or Apache error logs
        print("WARNING: App not configured. Visit /setup to initialize.")
    else:
        # Run DB initialization/migrations if configured
        try:
            init_db()
        except Exception as e:
            print(f"ERROR: Could not initialize database: {e}")
    return app
# WSGI entry point: Apache/mod_wsgi looks for an object named 'application'


application = create_app()
if __name__ == "__main__":
    # This block ONLY runs if you type 'python app.py'
    # Use application.run to ensure we use the instance returned by create_app()
    application.run(host="0.0.0.0", port=8000, debug=False)
