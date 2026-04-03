import re
import logging

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
)

from models import db, User, Profile

logger  = logging.getLogger("NthakaGuide.auth")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_ADMIN_ACCOUNTS = 2

# ── Known email domains ────────────────────────────────────────────────────────
# Covers the most common global and Malawian providers.
# The logic below also accepts *.edu, *.org, *.net, *.gov, *.ac.*, *.co.* TLDs
# so institutional addresses are handled generically.
_KNOWN_DOMAINS = {
    # Global webmail
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.za", "yahoo.com.au",
    "outlook.com", "outlook.co.uk",
    "hotmail.com", "hotmail.co.uk", "hotmail.fr",
    "live.com", "live.co.uk",
    "msn.com",
    "icloud.com", "me.com", "mac.com",
    "proton.me", "protonmail.com", "pm.me",
    "zoho.com",
    "aol.com",
    "yandex.com", "yandex.ru",
    # Malawi-specific
    "unima.ac.mw", "mzuni.ac.mw", "poly.ac.mw", "luanar.ac.mw",
    "gov.mw", "malawi.gov.mw",
    "africa.com", "mweb.co.za",
}

# TLDs / second-level domains we trust unconditionally
_TRUSTED_TLDS  = {"edu", "org", "net", "gov", "mil"}
_TRUSTED_SLDS  = {"ac", "gov", "edu", "org", "net", "co"}   # e.g. ac.mw, co.mw


def _is_known_domain(domain: str) -> bool:
    """Return True when the email domain is recognisable / trustworthy."""
    domain = domain.lower()

    if domain in _KNOWN_DOMAINS:
        return True

    parts = domain.split(".")
    if len(parts) < 2:
        return False

    tld = parts[-1]
    sld = parts[-2] if len(parts) >= 3 else ""

    # *.edu / *.org / *.net / *.gov
    if tld in _TRUSTED_TLDS:
        return True

    # *.ac.mw, *.gov.mw, *.co.mw, *.ac.uk, etc.
    if sld in _TRUSTED_SLDS:
        return True

    # Generic *.com or *.mw company domains  (e.g. company.com, nbs.mw)
    if tld in ("com", "mw"):
        return True

    return False


# ── Validators ─────────────────────────────────────────────────────────────────

def _validate_email(email: str) -> str | None:
    """
    Validate email format AND domain.
    Returns an error string or None if valid.
    """
    email = email.strip().lower()

    if not email:
        return "Email is required."

    # Basic structural check
    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "Enter a valid email address (e.g. name@gmail.com)."

    local, domain = parts

    # Local part: no leading/trailing dots, no consecutive dots
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return "The part before @ contains invalid characters."

    # Domain must contain at least one dot
    if "." not in domain:
        return "Email domain must include a dot (e.g. gmail.com)."

    # Domain must be a known/trusted provider
    if not _is_known_domain(domain):
        return (
            f'"{domain}" is not a recognised email provider. '
            "Use Gmail, Outlook, Yahoo, a university address, or similar."
        )

    return None


def _validate_phone(phone: str) -> str | None:
    """
    Malawi phone number: +265 followed by exactly 9 digits.
    The 9 digits must start with 8 or 9 (TNM/Airtel/others).
    Spaces inside the local part are stripped before checking.

    Valid examples:
        +265 999 000 000
        +265999000000
        +265 881234567
    """
    if not phone:
        return None  # phone is optional

    # Strip spaces for validation (we store the cleaned version)
    cleaned = phone.replace(" ", "")

    if not cleaned.startswith("+265"):
        return "Phone number must start with +265."

    local = cleaned[4:]  # digits after +265

    if not re.fullmatch(r"\d{9}", local):
        return "After +265, enter exactly 9 digits (e.g. +265 999 000 000)."

    if not re.match(r"^[89]", local):
        return "The 9 digits after +265 must start with 8 or 9 (e.g. 88x, 99x, 8xx, 9xx)."

    return None


def _validate_full_name(name: str) -> str | None:
    """
    Full name rules:
      • At least 2 characters
      • Must start with a letter
      • May contain letters, numbers, spaces, hyphens, apostrophes, and dots
      • Cannot be digits-only
    """
    if not name or not name.strip():
        return "Full name is required."

    name = name.strip()

    if len(name) < 2:
        return "Name must be at least 2 characters long."

    if re.fullmatch(r"\d+", name):
        return "Name cannot consist of numbers only."

    if not re.match(r"^[a-zA-Z]", name):
        return "Name must start with a letter."

    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9 .\'\-]*", name):
        return "Name may only contain letters, numbers, spaces, hyphens, apostrophes, and dots."

    return None


def _validate_password(password: str) -> str | None:
    """
    Password strength rules (identical to the frontend RULES list):
      • Minimum 8 characters
      • At least one lowercase letter
      • At least one uppercase letter
      • At least one digit
      • At least one special character
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


# ── Admin helpers ─────────────────────────────────────────────────────────────
def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code

def _admin_count() -> int:
    return User.query.filter_by(role="admin").count()

def _admin_slots_available() -> bool:
    return _admin_count() < MAX_ADMIN_ACCOUNTS


# ── GET /auth/admin-slots ─────────────────────────────────────────────────────
@auth_bp.route("/admin-slots", methods=["GET"])
def admin_slots():
    remaining = MAX_ADMIN_ACCOUNTS - _admin_count()
    return jsonify({
        "admin_registration_open": remaining > 0,
        "remaining_admin_slots":   max(0, remaining),
        "max_admin_accounts":      MAX_ADMIN_ACCOUNTS,
    })


# ── POST /auth/register ───────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    POST /auth/register
    Body (JSON):
        email       str  — required
        password    str  — required; must pass strength rules
        role        str  — "user" | "admin"  (optional, default "user")
        full_name   str  — required for new accounts
        phone       str  — optional; must be +265 followed by 9 digits starting with 8/9
        district    str  — optional

    Returns 201: { access_token, user, profile }
    """
    data = request.get_json(silent=True) or {}

    email     = (data.get("email")     or "").strip().lower()
    password  =  data.get("password")  or ""
    role      = (data.get("role")      or "user").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    phone     = (data.get("phone")     or "").strip()
    district  =  data.get("district")  or None

    # ── Field-by-field validation ──────────────────────────────────────────────
    email_err = _validate_email(email)
    if email_err:
        return _bad(email_err)

    name_err = _validate_full_name(full_name)
    if name_err:
        return _bad(name_err)

    pw_err = _validate_password(password)
    if pw_err:
        return _bad(pw_err)

    phone_err = _validate_phone(phone)
    if phone_err:
        return _bad(phone_err)

    # ── Normalise phone: store without spaces ──────────────────────────────────
    phone_clean = phone.replace(" ", "") if phone else None

    # ── Duplicate email ────────────────────────────────────────────────────────
    if User.query.filter_by(email=email).first():
        return _bad("An account with that email already exists.", 409)

    # ── Role guard ─────────────────────────────────────────────────────────────
    if role not in ("user", "admin"):
        role = "user"

    if role == "admin" and not _admin_slots_available():
        return _bad(
            f"The maximum number of admin accounts ({MAX_ADMIN_ACCOUNTS}) has been reached. "
            "Please register as a regular user.",
            403,
        )

    # ── Persist ────────────────────────────────────────────────────────────────
    user = User(
        email    = email,
        password = generate_password_hash(password),
        role     = role,
    )
    db.session.add(user)
    db.session.flush()   # get user.id before commit

    profile = Profile(
        user_id   = user.id,
        full_name = full_name or None,
        phone     = phone_clean or None,
        district  = district,
    )
    db.session.add(profile)
    db.session.commit()

    token = create_access_token(identity=user.id)
    logger.info("Registered: %s (role=%s, district=%s)", email, role, district)

    return jsonify({
        "message":      "Account created successfully.",
        "access_token": token,
        "user":         user.to_dict(),
        "profile":      profile.to_dict(),
    }), 201


# ── POST /auth/login ──────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /auth/login
    Body: { "email": str, "password": str }
    Returns: { access_token, user }
    """
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email")    or "").strip().lower()
    password =  data.get("password") or ""

    if not email or not password:
        return _bad("Email and password are required.")

    user = User.query.filter_by(email=email).first()

    if not user or not check_password_hash(user.password, password):
        return _bad("Invalid email or password.", 401)

    if not user.is_active:
        return _bad("Account is deactivated. Contact support.", 403)

    token = create_access_token(identity=user.id)
    logger.info("Login: %s (role=%s)", email, user.role)

    return jsonify({
        "message":      "Login successful.",
        "access_token": token,
        "user":         user.to_dict(),
    })


# ── GET /auth/me ──────────────────────────────────────────────────────────────
@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user    = User.query.get_or_404(user_id)
    profile = user.profile
    return jsonify({
        "user":    user.to_dict(),
        "profile": profile.to_dict() if profile else None,
    })


# ── PUT /auth/change-password ─────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["PUT"])
@jwt_required()
def change_password():
    """
    PUT /auth/change-password
    Body: { "old_password": str, "new_password": str }
    """
    user_id = get_jwt_identity()
    user    = User.query.get_or_404(user_id)
    data    = request.get_json(silent=True) or {}

    old_pw = data.get("old_password") or ""
    new_pw = data.get("new_password") or ""

    if not old_pw or not new_pw:
        return _bad("Both old_password and new_password are required.")

    if not check_password_hash(user.password, old_pw):
        return _bad("Current password is incorrect.", 401)

    pw_err = _validate_password(new_pw)
    if pw_err:
        return _bad(pw_err)

    user.password = generate_password_hash(new_pw)
    db.session.commit()
    logger.info("Password changed for user %s", user_id)
    return jsonify({"message": "Password updated successfully."})