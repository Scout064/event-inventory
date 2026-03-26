import re
from functools import wraps
from flask import (
    flash, redirect, url_for, current_app,
    g
)
from flask_login import current_user, UserMixin
from wtforms.validators import ValidationError


LEET_MAP = str.maketrans({
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
    "!": "i"
})

RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "system",
    "support",
    "security",
    "login",
    "logout",
    "signup",
    "register",
    "api",
    "user",
    "users",
    "null",
    "undefined",
    "none",
    "true",
    "false",
    "static",
    "assets",
    "config",
    "settings",
    "dashboard",
    "adminpanel"
}

RESERVED_PATTERNS = re.compile(
    r"(admin|administrator|root|superuser|sysadmin|moderator|staff|support|owner)"
)


class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin):
        self.id = str(id)
        self.username = username
        self.password_hash = password_hash
        self.is_admin = bool(is_admin)


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return current_app.login_manager.unauthorized()
        if not getattr(current_user, "is_admin", False):
            flash("Admin access required.", "warning")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper


def normalize_username(username: str) -> str:
    username = username.lower()
    username = username.translate(LEET_MAP)
    username = re.sub(r"[\W_]+", "", username)
    return username


def is_forbidden_username(username: str) -> bool:
    normalized = normalize_username(username)
    if normalized in RESERVED_USERNAMES:
        return True
    if RESERVED_PATTERNS.search(normalized):
        return True
    return False


class ReservedUsername:
    def __call__(self, form, field):
        # During initial setup no user is logged in — skip all checks
        if not current_user.is_authenticated:
            return
        # Allow admins to bypass
        if getattr(current_user, "is_admin", False):
            return
        username = field.data.strip()
        normalized = normalize_username(username)
        if normalized in RESERVED_USERNAMES:
            raise ValidationError("This username is reserved.")
        if RESERVED_PATTERNS.search(normalized):
            raise ValidationError("This username is too similar to an administrator account.")

