import os
import secrets
from dotenv import load_dotenv, set_key
from inventory_app.db import APP_DIR

DOTENV_PATH = os.path.join(APP_DIR, ".env")


def get_or_create_flask_secret():
    """
    Checks for a secure FLASK_SECRET_KEY.
    If missing, generates a new one and persists it to .env.
    """
    load_dotenv(DOTENV_PATH)
    current_key = os.environ.get("FLASK_SECRET_KEY")
    if not current_key:
        print("Notice: Missing FLASK_SECRET_KEY detected. Generating a secure replacement...")
        new_secret = secrets.token_hex(32)
        set_key(DOTENV_PATH, "FLASK_SECRET_KEY", new_secret)
        os.environ["FLASK_SECRET_KEY"] = new_secret
        return new_secret
    return current_key
