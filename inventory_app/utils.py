import os
from werkzeug.utils import secure_filename
from inventory_app.db import APP_DIR

UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
QR_DIR = os.path.join(APP_DIR, "static", "qr_codes")

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)


def save_logo(file):
    """Validates and saves the uploaded logo file."""
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg"]:
        raise ValueError("Invalid logo type")
    path = os.path.join(UPLOAD_DIR, "company_logo" + ext)
    file.save(path)
    return path
