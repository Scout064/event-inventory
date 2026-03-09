import os
import json
import mariadb


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
