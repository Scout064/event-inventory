\
import os
import json
import io
import re
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_login import LoginManager, login_user, logout_user, current_user, login_required, UserMixin
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, FileField, IntegerField
from wtforms.validators import DataRequired, Length, Optional
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import mariadb
import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    cur = conn.cursor()
    # Users: id, username unique, password hash, is_admin
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(128) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        is_admin BOOLEAN NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

    # Items
    cur.execute("""CREATE TABLE IF NOT EXISTS items (
        inventory_id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        category VARCHAR(128),
        description TEXT,
        serial_number VARCHAR(128),
        manufacturer VARCHAR(128),
        model VARCHAR(128)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

    # Productions (Locations / Events)
    cur.execute("""CREATE TABLE IF NOT EXISTS productions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        date DATE NULL,
        notes TEXT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

    # Assignment: items in productions
    cur.execute("""CREATE TABLE IF NOT EXISTS production_items (
        production_id INT NOT NULL,
        inventory_id VARCHAR(64) NOT NULL,
        PRIMARY KEY (production_id, inventory_id),
        FOREIGN KEY (production_id) REFERENCES productions(id) ON DELETE CASCADE,
        FOREIGN KEY (inventory_id) REFERENCES items(inventory_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;""")

    conn.commit()
    cur.close()
    conn.close()

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

login_manager = LoginManager(app)
login_manager.login_view = "login"

# HTTPS enforcement except LAN
LAN_REGEX = re.compile(r"^(127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+)$")

@app.before_request
def enforce_https():
    cfg = load_config()
    # If app not configured yet, allow setup over HTTP
    if not cfg.get("configured"):
        return
    # Determine if request is secure (behind Apache it's usually handled already).
    # Respect X-Forwarded-Proto if present.
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
    is_secure = request.is_secure or forwarded_proto == "https"
    remote_ip = request.remote_addr or ""
    if not is_secure and not LAN_REGEX.match(remote_ip):
        # Redirect to HTTPS
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)

# User model bridging Flask-Login and DB
class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin):
        self.id = str(id)
        self.username = username
        self.password_hash = password_hash
        self.is_admin = bool(is_admin)

def find_user_by_username(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return User(*row)
    return None

def find_user_by_id(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id=%s", (user_id,))
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

# Forms
class SetupForm(FlaskForm):
    db_host = StringField("DB Host", validators=[DataRequired()], default="localhost")
    db_port = StringField("DB Port", validators=[DataRequired()], default="3306")
    db_name = StringField("DB Name", validators=[DataRequired()], default="inventory_db")
    db_user = StringField("DB User", validators=[DataRequired()], default="inventory_user")
    db_pass = PasswordField("DB Password", validators=[DataRequired()])
    admin_username = StringField("Admin Username", validators=[DataRequired(), Length(min=3, max=128)], default="admin")
    admin_password = PasswordField("Admin Password", validators=[DataRequired(), Length(min=6)])
    default_user_username = StringField("Default User Username", validators=[Optional(), Length(min=3, max=128)])
    default_user_password = PasswordField("Default User Password", validators=[Optional(), Length(min=6)])
    company_logo = FileField("Company Logo (PNG/JPEG)")
    submit = SubmitField("Initialize")

class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")

class ItemForm(FlaskForm):
    inventory_id = StringField("Inventory ID", validators=[DataRequired(), Length(min=1, max=64)])
    name = StringField("Name", validators=[DataRequired(), Length(min=1, max=255)])
    category = StringField("Category", validators=[Optional(), Length(max=128)])
    description = TextAreaField("Description", validators=[Optional()])
    serial_number = StringField("Serial Number", validators=[Optional(), Length(max=128)])
    manufacturer = StringField("Manufacturer", validators=[Optional(), Length(max=128)])
    model = StringField("Model", validators=[Optional(), Length(max=128)])
    submit = SubmitField("Save")

class ProductionForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(min=1, max=255)])
    date = StringField("Date (YYYY-MM-DD)", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional()])
    submit = SubmitField("Save")

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

# Routes
@app.route("/setup", methods=["GET", "POST"])
def setup():
    cfg = load_config()
    if cfg.get("configured"):
        return redirect(url_for("index"))
    form = SetupForm()
    if form.validate_on_submit():
        # Save config
        logo_path = None
        file = form.company_logo.data
        if file:
            filename = secure_filename(file.filename)
            if filename:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in [".png", ".jpg", ".jpeg"]:
                    flash("Logo must be PNG or JPEG.", "danger")
                    return render_template("setup.html", form=form, configured=False)
                logo_path = os.path.join(UPLOAD_DIR, "company_logo" + ext)
                file.save(logo_path)

        new_cfg = {
            "configured": True,
            "db_host": form.db_host.data.strip(),
            "db_port": form.db_port.data.strip(),
            "db_name": form.db_name.data.strip(),
            "db_user": form.db_user.data.strip(),
            "db_pass": form.db_pass.data,
            "logo_path": logo_path,
        }
        # Test DB and create tables
        try:
            with mariadb.connect(
                user=new_cfg["db_user"],
                password=new_cfg["db_pass"],
                host=new_cfg["db_host"],
                port=int(new_cfg["db_port"]),
                database=new_cfg["db_name"],
            ) as _:
                pass
        except mariadb.Error as ex:
            flash(f"Database connection failed: {ex}", "danger")
            return render_template("setup.html", form=form, configured=False)

        save_config(new_cfg)
        init_db()
        # Create admin user
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username=%s", (form.admin_username.data,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s,%s,%s)",
                        (form.admin_username.data, generate_password_hash(form.admin_password.data), True))
        # Optional default user
        if form.default_user_username.data and form.default_user_password.data:
            cur.execute("SELECT id FROM users WHERE username=%s", (form.default_user_username.data,))
            if not cur.fetchone():
                cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s,%s,%s)",
                            (form.default_user_username.data, generate_password_hash(form.default_user_password.data), False))
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
@app.route("/items")
@login_required
def items():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT inventory_id, name, category, serial_number, manufacturer, model FROM items ORDER BY name")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("items.html", rows=rows)

@app.route("/items/new", methods=["GET","POST"])
@login_required
def items_new():
    form = ItemForm()
    if form.validate_on_submit():
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""INSERT INTO items (inventory_id,name,category,description,serial_number,manufacturer,model)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                        (form.inventory_id.data.strip(), form.name.data.strip(), form.category.data.strip() if form.category.data else None,
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

            # ✅ Always regenerate QR after update
            cfg = load_config()
            logo_path = cfg.get("logo_path") or "uploads/company_logo.png"  # fallback

            qr_data_text = (
                f"ID: {inventory_id}\n"
                f"Name: {form.name.data.strip()}\n"
                f"Category: {form.category.data.strip() if form.category.data else ''}\n"
                f"SN: {form.serial_number.data.strip() if form.serial_number.data else ''}\n"
                f"Manufacturer: {form.manufacturer.data.strip() if form.manufacturer.data else ''}\n"
                f"Model: {form.model.data.strip() if form.model.data else ''}"
            )

            img = generate_qr_with_logo(qr_data_text, logo_path)
            qr_path = Path("static/qr_codes") / f"{inventory_id}.png"
            qr_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(qr_path)

            flash("Item updated and QR code regenerated.", "success")
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

@app.route("/productions/new", methods=["GET","POST"])
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

@app.route("/productions/<int:pid>/edit", methods=["GET","POST"])
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
        cur.execute("INSERT IGNORE INTO production_items (production_id, inventory_id) VALUES (%s,%s)", (pid, inventory_id))
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
    # Create a simple label: QR + text lines
    cfg = load_config()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, manufacturer, model FROM items WHERE inventory_id=%s", (inventory_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404)
    qr = generate_qr_with_logo(inventory_id, cfg.get("logo_path"))
    # Compose label image (100mm x 54mm at 300dpi ~ 1181 x 637 px)
    dpi = 300
    width_px = int((100/25.4)*dpi)
    height_px = int((54/25.4)*dpi)
    label = Image.new("RGB", (width_px, height_px), "white")
    # Paste QR at left
    qr_size = int(height_px * 0.9)
    qr = qr.resize((qr_size, qr_size), Image.LANCZOS)
    label.paste(qr, (int(height_px*0.05), int(height_px*0.05)))
    # Draw text
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(label)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(height_px*0.1))
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", int(height_px*0.08))
    except:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
    x = qr_size + int(height_px*0.1)
    y = int(height_px*0.12)
    draw.text((x, y), f"{inventory_id}", font=font, fill="black")
    y += int(height_px*0.16)
    draw.text((x, y), f"{row[0]}", font=font_small, fill="black")
    y += int(height_px*0.12)
    draw.text((x, y), f"{row[1] or ''} {row[2] or ''}".strip(), font=font_small, fill="black")
    # Output PNG
    bio = io.BytesIO()
    label.save(bio, format="PNG")
    bio.seek(0)
    return send_file(bio, mimetype="image/png", as_attachment=False, download_name=f"{inventory_id}.png")

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
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 20*mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, y, "Item Inventory Report")
    y -= 10*mm
    c.setFont("Helvetica", 10)
    for r in rows:
        line = f"{r[0]} | {r[1]} | {r[2] or ''} | SN:{r[3] or ''} | {r[4] or ''} {r[5] or ''}"
        if y < 20*mm:
            c.showPage()
            y = height - 20*mm
            c.setFont("Helvetica", 10)
        c.drawString(15*mm, y, line[:120])
        y -= 6*mm
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
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 20*mm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, y, f"BOM – {prod[1]}")
    y -= 8*mm
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, y, f"Date: {prod[2] or ''}")
    y -= 6*mm
    if prod[3]:
        c.drawString(20*mm, y, f"Notes: {prod[3][:90]}")
        y -= 8*mm
    c.setFont("Helvetica", 10)
    for r in items:
        if y < 20*mm:
            c.showPage()
            y = height - 20*mm
            c.setFont("Helvetica", 10)
        line = f"{r[0]} | {r[1]} | {r[2] or ''} | SN:{r[3] or ''} | {r[4] or ''} {r[5] or ''}"
        c.drawString(15*mm, y, line[:120])
        y -= 6*mm
    c.showPage()
    c.save()
    bio.seek(0)
    return send_file(bio, mimetype="application/pdf", as_attachment=True, download_name=f"production_{pid}_BOM.pdf")

# Admin-only simple settings (logo update)
@app.route("/admin/settings", methods=["GET","POST"])
@login_required
@admin_required
def admin_settings():
    cfg = load_config()
    if request.method == "POST":
        file = request.files.get("company_logo")
        if file and file.filename:
            filename = secure_filename(file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in [".png", ".jpg", ".jpeg"]:
                flash("Logo must be PNG or JPEG.", "danger")
                return redirect(url_for("admin_settings"))
            logo_path = os.path.join(UPLOAD_DIR, "company_logo" + ext)
            file.save(logo_path)
            cfg["logo_path"] = logo_path
            save_config(cfg)
            flash("Logo updated.", "success")
    return render_template("admin_settings.html", cfg=cfg)

if __name__ == "__main__":
    cfg = load_config()
    if not cfg.get("configured"):
        # guide to /setup
        print("App not configured. Visit /setup to initialize.")
    else:
        init_db()
    app.run(host="0.0.0.0", port=8000, debug=True)

# Optional: static serving of uploads in dev
from flask import send_from_directory
@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory('uploads', filename)

