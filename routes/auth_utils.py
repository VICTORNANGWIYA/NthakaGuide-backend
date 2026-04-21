# routes/auth_utils.py
# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers used by both auth.py and auth_reset.py.
# Kept in a separate file to avoid circular imports.
# ─────────────────────────────────────────────────────────────────────────────

import re
from flask import jsonify


def _bad(msg: str, code: int = 400):
    """Return a JSON error response."""
    return jsonify({"error": msg}), code


def _validate_password(password: str) -> str | None:
    """
    Password strength rules (must match the frontend PASSWORD_RULES list):
      • Minimum 8 characters
      • At least one lowercase letter
      • At least one uppercase letter
      • At least one digit
      • At least one special character
    Returns an error string or None if valid.
    """
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[a-z]", password):
        return "Password must contain at least one lowercase letter."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"\d", password):
        return "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{}|;':\",./<>?\\`~]", password):
        return "Password must contain at least one special character (e.g. !@#$%)."
    return None