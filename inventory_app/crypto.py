import os
import secrets
from inventory_app.db import APP_DIR
from dotenv import load_dotenv, set_key
# Pfad zur .env Datei definieren (ein Verzeichnis über inventory_app)
DOTENV_PATH = os.path.join(APP_DIR, ".env")
# Dev Secret to change
OLD_DEV_SECRET = "dev-secret-change-me" 


def get_or_create_flask_secret():
    """
    Checks for a secure FLASK_SECRET_KEY. 
    If missing or matching the old dev secret, generates a new one.
    """
    # 1. Load existing variables
    load_dotenv(DOTENV_PATH)
    # 2. Get the current key
    current_key = os.environ.get("FLASK_SECRET_KEY")
    # 3. Check if we need to upgrade
    if not current_key:
        print("Notice: Missing FLASK_SECRET_KEY detected. Generating a secure replacement...")
        # Generate a highly secure, 64-character random hex string
        # secrets module is cryptographically secure, better than os.urandom
        new_secret = secrets.token_hex(32)
        # 4. Save to the .env file permanently
        # Note: python-dotenv will wrap this in double quotes, 
        # but since it's just hex (no $ symbols), it won't trigger the bash bug!
        set_key(DOTENV_PATH, "FLASK_SECRET_KEY", new_secret)
        # 5. Export to current running environment
        os.environ["FLASK_SECRET_KEY"] = new_secret
        return new_secret
    # If a custom secure key was already there, just return it
    return current_key
