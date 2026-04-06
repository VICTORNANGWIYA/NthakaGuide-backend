# routes/auth.py
# ─────────────────────────────────────────────────────────────────────────────
# Authentication routes: register, login, me, change-password, delete-account.
#
# Welcome emails and password-changed emails are fired in daemon threads so
# they never block the HTTP response — even on a slow network the user gets
# their JWT immediately after registration.
# ─────────────────────────────────────────────────────────────────────────────

import re
import logging
import threading

from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
)

from models import db, User, Profile
from routes.auth_utils import _validate_password, _bad

logger  = logging.getLogger("NthakaGuide.auth")
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# ── Constants ──────────────────────────────────────────────────────────────────
MAX_ADMIN_ACCOUNTS = 2

# ── Known email domains ────────────────────────────────────────────────────────
_KNOWN_DOMAINS = {
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
    "unima.ac.mw", "mzuni.ac.mw", "poly.ac.mw", "luanar.ac.mw",
    "gov.mw", "malawi.gov.mw",
    "africa.com", "mweb.co.za",
}

_TRUSTED_TLDS = {"edu", "org", "net", "gov", "mil"}
_TRUSTED_SLDS = {"ac", "gov", "edu", "org", "net", "co"}


def _is_known_domain(domain: str) -> bool:
    domain = domain.lower()
    if domain in _KNOWN_DOMAINS:
        return True
    parts = domain.split(".")
    if len(parts) < 2:
        return False
    tld = parts[-1]
    sld = parts[-2] if len(parts) >= 3 else ""
    if tld in _TRUSTED_TLDS:
        return True
    if sld in _TRUSTED_SLDS:
        return True
    if tld in ("com", "mw"):
        return True
    return False


# ── Validators ─────────────────────────────────────────────────────────────────

def _validate_email(email: str) -> str | None:
    email = email.strip().lower()
    if not email:
        return "Email is required."
    parts = email.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "Enter a valid email address (e.g. name@gmail.com)."
    local, domain = parts
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return "The part before @ contains invalid characters."
    if "." not in domain:
        return "Email domain must include a dot (e.g. gmail.com)."
    if not _is_known_domain(domain):
        return (
            f'"{domain}" is not a recognised email provider. '
            "Use Gmail, Outlook, Yahoo, a university address, or similar."
        )
    return None


def _validate_phone(phone: str) -> str | None:
    if not phone:
        return None
    cleaned = phone.replace(" ", "")
    if not cleaned.startswith("+265"):
        return "Phone number must start with +265."
    local = cleaned[4:]
    if not re.fullmatch(r"\d{9}", local):
        return "After +265, enter exactly 9 digits (e.g. +265 999 000 000)."
    if not re.match(r"^[89]", local):
        return "The 9 digits after +265 must start with 8 or 9 (e.g. 88x, 99x, 8xx, 9xx)."
    return None


def _validate_full_name(name: str) -> str | None:
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


# ── Admin helpers ──────────────────────────────────────────────────────────────

def _admin_count() -> int:
    return User.query.filter_by(role="admin").count()

def _admin_slots_available() -> bool:
    return _admin_count() < MAX_ADMIN_ACCOUNTS


# ── Background email helper ────────────────────────────────────────────────────

def _fire_email(fn, *args) -> None:
    """
    Run *fn(*args)* in a daemon thread so the HTTP response is never blocked.
    Errors inside fn are already caught and logged by the email functions.
    """
    threading.Thread(target=fn, args=args, daemon=True).start()


# ── GET /auth/admin-slots ──────────────────────────────────────────────────────
@auth_bp.route("/admin-slots", methods=["GET"])
def admin_slots():
    remaining = MAX_ADMIN_ACCOUNTS - _admin_count()
    return jsonify({
        "admin_registration_open": remaining > 0,
        "remaining_admin_slots":   max(0, remaining),
        "max_admin_accounts":      MAX_ADMIN_ACCOUNTS,
    })


# ── POST /auth/register ────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST"])
def register():
    """
    POST /auth/register
    Body: { email, password, role?, full_name, phone?, district? }
    Returns 201: { access_token, user, profile }

    Account is created and the JWT is returned immediately.
    The welcome email is sent in a background thread — network latency or SMTP
    failures never delay or break account creation.
    """
    data = request.get_json(silent=True) or {}

    email     = (data.get("email")     or "").strip().lower()
    password  =  data.get("password")  or ""
    role      = (data.get("role")      or "user").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    phone     = (data.get("phone")     or "").strip()
    district  =  data.get("district")  or None

    # ── Validation ─────────────────────────────────────────────────────────────
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

    phone_clean = phone.replace(" ", "") if phone else None

    if User.query.filter_by(email=email).first():
        return _bad("An account with that email already exists.", 409)

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

    # ── Welcome email in background — never blocks the response ───────────────
    from routes.auth_reset import send_welcome_email
    _fire_email(send_welcome_email, email, full_name or None)

    return jsonify({
        "message":      "Account created successfully.",
        "access_token": token,
        "user":         user.to_dict(),
        "profile":      profile.to_dict(),
    }), 201


# ── POST /auth/login ───────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    """
    POST /auth/login
    Body: { email, password }
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


# ── GET /auth/me ───────────────────────────────────────────────────────────────
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


# ── DELETE /auth/delete-account ───────────────────────────────────────────────
@auth_bp.route("/delete-account", methods=["DELETE"])
@jwt_required()
def delete_account():
    """
    DELETE /auth/delete-account
    Body: { password }  — requires password confirmation for safety.
    """
    user_id  = get_jwt_identity()
    user     = User.query.get_or_404(user_id)
    data     = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    if not password:
        return _bad("Password is required to delete your account.")
    if not check_password_hash(user.password, password):
        return _bad("Incorrect password.", 401)

    db.session.delete(user)   # cascade handles Profile via FK
    db.session.commit()
    logger.info("Account deleted: user_id=%s", user_id)
    return jsonify({"message": "Account deleted successfully."})


# ── PUT /auth/change-password ──────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["PUT"])
@jwt_required()
def change_password():
    """
    PUT /auth/change-password
    Body: { old_password, new_password }

    Password-changed confirmation email is sent in a background thread.
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

    if check_password_hash(user.password, new_pw):
        return _bad("New password must be different from your current password.")

    user.password = generate_password_hash(new_pw)
    db.session.commit()
    logger.info("Password changed for user %s", user_id)

    # ── Confirmation email in background — never blocks the response ───────────
    from routes.auth_reset import send_password_changed_email
    full_name = user.profile.full_name if user.profile else None
    _fire_email(send_password_changed_email, user.email, full_name)

    return jsonify({"message": "Password updated successfully."})