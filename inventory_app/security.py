import re
from flask_login import current_user
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
        username = field.data.strip()
        normalized = normalize_username(username)
        # Allow admins to bypass
        if getattr(current_user, "is_admin", False):
            return
        if normalized in RESERVED_USERNAMES:
            raise ValidationError("This username is reserved.")
        if RESERVED_PATTERNS.search(normalized):
            raise ValidationError("This username is too similar to an administrator account.")
