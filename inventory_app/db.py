import os
import json
import mariadb
from werkzeug.security import generate_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")


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
    try:
        conn = mariadb.connect(
            user=cfg["db_user"],
            password=cfg["db_pass"],
            host=cfg["db_host"],
            port=int(cfg.get("db_port", 3306)),
            database=cfg["db_name"],
        )
        return conn
    except mariadb.Error:
        return None


def init_db():
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()
    schema_path = os.path.join(APP_DIR, "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path, "r") as f:
            sql_commands = f.read().split(';')
        for command in sql_commands:
            if command.strip():
                try:
                    cur.execute(command)
                except mariadb.Error as e:
                    print(f"Error executing command: {e}")
        conn.commit()
    cur.close()
    conn.close()


def get_item_suggestions():
    """Helper to fetch distinct values for autocomplete suggestions."""
    conn = get_db()
    if not conn:
        return {}
    cur = conn.cursor()
    suggestions = {}
    for field in ['category', 'manufacturer', 'model']:
        cur.execute(f"SELECT DISTINCT {field} FROM items WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}")
        suggestions[field] = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return suggestions


def find_user_by_username(username):
    conn = get_db()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username=%s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def find_user_by_id(user_id):
    conn = get_db()
    if not conn: return None
    cur = conn.cursor()
    cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id=%s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

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

def _execute_profile_update(cur, user_id, uname, rname, email, bday, pw_hash=None):
    if pw_hash:
        query = "UPDATE users SET username=%s, real_name=%s, email=%s, birthday=%s, password_hash=%s WHERE id=%s"
        params = (uname, rname, email, bday, pw_hash, user_id)
    else:
        query = "UPDATE users SET username=%s, real_name=%s, email=%s, birthday=%s WHERE id=%s"
        params = (uname, rname, email, bday, user_id)
    cur.execute(query, params)

def process_item_row(cur, row):
    cleaned = {k: (v.strip() if v else '') for k, v in row.items() if k}
    if not any(cleaned.values()): return 0
    inv_id, name = cleaned.get('inventory_id', ''), cleaned.get('name', '')
    if not inv_id or not name: return 3
    try:
        cur.execute("""
            INSERT INTO items (inventory_id, name, category, description, serial_number, manufacturer, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (inv_id, name, cleaned.get('category') or None, cleaned.get('description') or None, cleaned.get('serial_number') or None, cleaned.get('manufacturer') or None, cleaned.get('model') or None))
        return 1
    except mariadb.IntegrityError as ie:
        return 2 if ie.errno == 1062 else 3
    except Exception as e:
        print(f"Row Exception: {e}")
        return 3
