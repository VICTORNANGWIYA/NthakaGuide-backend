# routes/auth_reset.py
# ─────────────────────────────────────────────────────────────────────────────
# Password-reset flow  +  all transactional emails for NthakaGuide.
#
# EVERY outbound email function (send_welcome_email, send_password_changed_email,
# etc.) is designed to be called from a daemon thread via auth.py's _fire_email()
# helper — they NEVER raise, only log warnings on failure.
#
# The OTP email in forgot_password() IS sent synchronously because the user is
# actively waiting for the code and we need to surface errors immediately.
#
# Endpoints:
#   POST /auth/forgot-password   — send OTP
#   POST /auth/verify-otp        — verify OTP → return reset_token
#   POST /auth/reset-password    — set new password
# ─────────────────────────────────────────────────────────────────────────────

import os
import secrets
import logging
import smtplib
import threading

from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

import jwt
from flask             import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash

from models          import db, User
from routes.auth_utils import _validate_password, _bad

logger   = logging.getLogger("NthakaGuide.reset")
reset_bp = Blueprint("reset", __name__, url_prefix="/auth")

# ── OTP store (swap for Redis in production) ──────────────────────────────────
_OTP_STORE: dict[str, dict] = {}

OTP_TTL_SECONDS = 600    # 10 minutes
OTP_LENGTH      = 6
RESET_TOKEN_TTL = 900    # 15 minutes


# ─────────────────────────────────────────────────────────────────────────────
# SMTP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_cfg() -> dict:
    """
    Pull SMTP settings from Flask app config when inside a request context,
    otherwise fall back to os.getenv (needed for background threads which have
    no Flask application context).
    """
    try:
        # Inside a request/app context — use Flask config (most reliable)
        return {
            "server":   current_app.config.get("MAIL_SERVER",   "smtp.gmail.com"),
            "port":     int(current_app.config.get("MAIL_PORT", 587)),
            "username": current_app.config.get("MAIL_USERNAME", ""),
            "password": current_app.config.get("MAIL_PASSWORD", ""),
        }
    except RuntimeError:
        # Background thread — no app context, read env directly
        return {
            "server":   os.getenv("MAIL_SERVER",   "smtp.gmail.com"),
            "port":     int(os.getenv("MAIL_PORT", "587")),
            "username": os.getenv("MAIL_USERNAME", ""),
            "password": os.getenv("MAIL_PASSWORD", ""),
        }


def _send_raw(msg: MIMEMultipart) -> None:
    """
    Lowest-level send via STARTTLS.
    Raises on failure — callers decide whether to log or re-raise.
    """
    cfg = _smtp_cfg()
    if not cfg["username"] or not cfg["password"]:
        raise RuntimeError(
            "MAIL_USERNAME and MAIL_PASSWORD are not set. "
            "Add them to your .env file."
        )
    with smtplib.SMTP(cfg["server"], cfg["port"], timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(cfg["username"], cfg["password"])
        smtp.sendmail(cfg["username"], msg["To"], msg.as_string())


def _base_msg(to_email: str, subject: str) -> MIMEMultipart:
    """Build a MIMEMultipart with headers pre-filled."""
    cfg            = _smtp_cfg()
    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"NthakaGuide <{cfg['username']}>"
    msg["To"]      = to_email
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# Shared HTML template
# ─────────────────────────────────────────────────────────────────────────────

# Logo hosted on Cloudinary — survives in all email clients without base64 bloat
LOGO_TAG = (
    '<img src="https://res.cloudinary.com/drct2cpcw/image/upload/'
    'v1775390138/logo_zvnzhx.jpg" '
    'alt="NthakaGuide" style="height:64px; width:auto;" />'
)

_YEAR = datetime.now().year

_CSS = """
body      { font-family:'Segoe UI',Arial,sans-serif; background:#f4f4f4; margin:0; padding:0; }
.wrapper  { max-width:520px; margin:40px auto; background:#ffffff;
             border-radius:10px; overflow:hidden;
             box-shadow:0 2px 12px rgba(0,0,0,.10); }
.header   { background:#2d6a4f; padding:20px 32px; text-align:center; }
.tagline  { color:#a8d5b5; margin:6px 0 0; font-size:12px;
             letter-spacing:2px; text-transform:uppercase; }
.subject  { color:#ffffff; margin:10px 0 0; font-size:15px; font-weight:600; }
.body     { padding:32px; color:#333333; line-height:1.6; }
.greeting { font-size:16px; margin-bottom:16px; }
.footer   { background:#f9f9f9; text-align:center; padding:16px;
             font-size:12px; color:#aaaaaa; border-top:1px solid #eeeeee; }
.otp-box  { background:#f0faf5; border:2px dashed #2d6a4f; border-radius:8px;
             text-align:center; padding:20px; margin:24px 0; }
.otp-box span { font-size:36px; font-weight:700; letter-spacing:10px;
                 color:#2d6a4f; font-family:monospace; }
.highlight{ background:#f0faf5; border-left:4px solid #2d6a4f;
             padding:12px 16px; border-radius:4px; margin:16px 0; }
.note     { font-size:13px; color:#888888; margin-top:24px; }
ul        { padding-left:20px; }
li        { margin-bottom:6px; }
"""


def _wrap(subject_label: str, body_html: str) -> str:
    """Wrap a body fragment in the full branded HTML shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>{_CSS}</style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      {LOGO_TAG}
      <p class="tagline">Smart Farming Solutions</p>
      <p class="subject">{subject_label}</p>
    </div>
    <div class="body">
      {body_html}
    </div>
    <div class="footer">© {_YEAR} NthakaGuide · Malawi</div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Background email dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def _fire_email(fn, *args) -> None:
    """Run fn(*args) in a daemon thread — errors are caught inside fn."""
    threading.Thread(target=fn, args=args, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL 1 — OTP / Password Reset
# (sent synchronously — user is waiting for the code)
# ─────────────────────────────────────────────────────────────────────────────

def _build_otp_email(to_email: str, otp: str, full_name: str | None) -> MIMEMultipart:
    first    = full_name.split()[0] if full_name else None
    greeting = f"Hi {first}," if first else "Hello,"

    plain = (
        f"{greeting}\n\n"
        f"Your NthakaGuide password-reset code is:\n\n"
        f"    {otp}\n\n"
        f"This code expires in {OTP_TTL_SECONDS // 60} minutes.\n"
        f"If you did not request a reset, please ignore this email.\n\n"
        f"— The NthakaGuide Team"
    )

    body_html = f"""
      <p class="greeting">{greeting}</p>
      <p>We received a request to reset the password for your NthakaGuide account.
         Use the code below. It expires in
         <strong>{OTP_TTL_SECONDS // 60} minutes</strong>.</p>
      <div class="otp-box"><span>{otp}</span></div>
      <p>Enter this code on the reset page. Do <strong>not</strong> share it
         with anyone.</p>
      <p class="note">If you did not request a password reset, please ignore this
         email. Your account remains secure.</p>
    """

    msg = _base_msg(to_email, "Your NthakaGuide password-reset code")
    msg.attach(MIMEText(plain,                              "plain"))
    msg.attach(MIMEText(_wrap("Password Reset", body_html), "html"))
    return msg


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL 2 — Welcome (called from auth.py via _fire_email — background thread)
# ─────────────────────────────────────────────────────────────────────────────

def send_welcome_email(to_email: str, full_name: str | None) -> None:
    """
    Send a welcome email after successful account creation.
    Designed to run in a background thread — NEVER raises, only logs.
    """
    first    = full_name.split()[0] if full_name else "Farmer"
    greeting = f"Welcome, {first}!"

    plain = (
        f"Hi {first},\n\n"
        f"Welcome to NthakaGuide — Malawi's smart farming assistant!\n\n"
        f"Here is what you can do:\n"
        f"  • Get personalised crop recommendations for your district\n"
        f"  • Receive fertiliser plans tailored to your soil\n"
        f"  • Check pest and disease risk forecasts\n"
        f"  • Track your analysis history\n"
        f"  • Chat with our AI agricultural advisor\n\n"
        f"Log in at any time to start your first soil analysis.\n\n"
        f"Happy farming!\n"
        f"— The NthakaGuide Team"
    )

    body_html = f"""
      <p class="greeting">{greeting}</p>
      <p>You have successfully created your NthakaGuide account.
         We are delighted to have you as part of Malawi's smart farming community.</p>
      <div class="highlight">
        <strong>Here is what you can do with NthakaGuide:</strong>
        <ul>
          <li> Get <strong>personalised crop recommendations</strong> for your district</li>
          <li> Receive <strong>fertiliser plans</strong> tailored to your soil</li>
         <li> Track your <strong>analysis history</strong> over time</li>
          <li> Chat with our <strong>AI agricultural advisor</strong></li>
        </ul>
      </div>
      <p>Log in at any time to start your first soil analysis and get your
         personalised crop recommendations.</p>
      <p style="margin-top:24px;">Happy farming!</p>
    """

    try:
        msg = _base_msg(to_email, "Welcome to NthakaGuide! ")
        msg.attach(MIMEText(plain,                           "plain"))
        msg.attach(MIMEText(_wrap("Welcome!", body_html),    "html"))
        _send_raw(msg)
        logger.info("Welcome email sent to %s", to_email)
    except Exception as exc:
        # Never crash — account is already created
        logger.warning("Welcome email failed for %s: %s", to_email, exc)


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL 3 — Password Changed (background thread)
# ─────────────────────────────────────────────────────────────────────────────

def send_password_changed_email(to_email: str, full_name: str | None) -> None:
    """
    Send a security confirmation after a password change or reset.
    Designed to run in a background thread — NEVER raises, only logs.
    """
    first    = full_name.split()[0] if full_name else "there"
    greeting = f"Hi {first},"
    when     = datetime.now().strftime("%d %B %Y at %H:%M UTC")

    plain = (
        f"{greeting}\n\n"
        f"Your NthakaGuide password was changed successfully on {when}.\n\n"
        f"If you made this change, no action is needed.\n\n"
        f"If you did NOT make this change, please reset your password immediately\n"
        f"using the 'Forgot Password' option on the login page.\n\n"
        f"— The NthakaGuide Security Team"
    )

    body_html = f"""
      <p class="greeting">{greeting}</p>
      <p>Your <strong>NthakaGuide password was changed successfully</strong>
         on {when}.</p>
      <div class="highlight">
        ✅ If <strong>you</strong> made this change — no action is needed.
           You are all set.
      </div>
      <p>⚠️ If you did <strong>not</strong> make this change, your account may be
         compromised. Please reset your password immediately using the
         <strong>Forgot Password</strong> option on the login page.</p>
      <p class="note">For your security, use a strong, unique password that you do
         not reuse on other websites.</p>
    """

    try:
        msg = _base_msg(to_email, "Your NthakaGuide password was changed")
        msg.attach(MIMEText(plain,                                     "plain"))
        msg.attach(MIMEText(_wrap("Password Changed", body_html),      "html"))
        _send_raw(msg)
        logger.info("Password-changed email sent to %s", to_email)
    except Exception as exc:
        logger.warning("Password-changed email failed for %s: %s", to_email, exc)


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL 4 — Account Deactivated (background thread)
# ─────────────────────────────────────────────────────────────────────────────

def send_account_deactivated_email(to_email: str, full_name: str | None) -> None:
    """Call from admin routes when deactivating a user account."""
    first    = full_name.split()[0] if full_name else "there"
    greeting = f"Hi {first},"

    plain = (
        f"{greeting}\n\n"
        f"Your NthakaGuide account has been temporarily deactivated.\n\n"
        f"If you believe this is a mistake, please contact our support team\n"
        f"by replying to this email.\n\n"
        f"— The NthakaGuide Team"
    )

    body_html = f"""
      <p class="greeting">{greeting}</p>
      <p>Your NthakaGuide account has been
         <strong>temporarily deactivated</strong>.</p>
      <div class="highlight">
        You will not be able to log in until your account is reactivated.
      </div>
      <p>If you believe this is a mistake or would like more information,
         please contact our support team by replying to this email.</p>
      <p class="note">We apologise for any inconvenience caused.</p>
    """

    try:
        msg = _base_msg(to_email, "Your NthakaGuide account has been deactivated")
        msg.attach(MIMEText(plain,                                        "plain"))
        msg.attach(MIMEText(_wrap("Account Deactivated", body_html),      "html"))
        _send_raw(msg)
        logger.info("Deactivation email sent to %s", to_email)
    except Exception as exc:
        logger.warning("Deactivation email failed for %s: %s", to_email, exc)


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL 5 — Account Reactivated (background thread)
# ─────────────────────────────────────────────────────────────────────────────

def send_account_reactivated_email(to_email: str, full_name: str | None) -> None:
    """Call from admin routes when reactivating a user account."""
    first    = full_name.split()[0] if full_name else "there"
    greeting = f"Hi {first},"

    plain = (
        f"{greeting}\n\n"
        f"Good news! Your NthakaGuide account has been reactivated.\n\n"
        f"You can now log in and continue using all features.\n\n"
        f"Happy farming!\n"
        f"— The NthakaGuide Team"
    )

    body_html = f"""
      <p class="greeting">{greeting}</p>
      <p>Your NthakaGuide account has been <strong>reactivated</strong>. 🎉</p>
      <div class="highlight">
        You can now log in and access all features of NthakaGuide again.
      </div>
      <p>If you have any questions, please reply to this email.</p>
      <p style="margin-top:24px;">Happy farming! 🌱</p>
    """

    try:
        msg = _base_msg(to_email, "Your NthakaGuide account has been reactivated")
        msg.attach(MIMEText(plain,                                          "plain"))
        msg.attach(MIMEText(_wrap("Account Reactivated", body_html),        "html"))
        _send_raw(msg)
        logger.info("Reactivation email sent to %s", to_email)
    except Exception as exc:
        logger.warning("Reactivation email failed for %s: %s", to_email, exc)


# ─────────────────────────────────────────────────────────────────────────────
# JWT helpers
# ─────────────────────────────────────────────────────────────────────────────

def _secret() -> str:
    """Resolve the signing secret from Flask config or env."""
    try:
        return str(
            current_app.config.get("SECRET_KEY")
            or current_app.config.get("JWT_SECRET_KEY")
            or os.getenv("JWT_SECRET", "change-me-in-production")
        )
    except RuntimeError:
        return str(os.getenv("JWT_SECRET", "change-me-in-production"))


def _make_reset_token(email: str) -> str:
    payload = {
        "sub":     email,
        "purpose": "pw_reset",
        "exp":     datetime.now(timezone.utc) + timedelta(seconds=RESET_TOKEN_TTL),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def _decode_reset_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
        if payload.get("purpose") != "pw_reset":
            return None
        return payload["sub"]
    except jwt.PyJWTError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@reset_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    """
    POST /auth/forgot-password
    Body: { email }
    Generates a 6-digit OTP and emails it.
    Always returns 200 (prevents user enumeration).
    """
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return _bad("Email is required.")

    SUCCESS_MSG = (
        "If that email is registered, a reset code has been sent. "
        "Check your inbox (and spam folder)."
    )

    user = User.query.filter_by(email=email).first()
    if not user:
        logger.info("forgot-password: unknown email %s", email)
        return jsonify({"message": SUCCESS_MSG}), 200

    otp = "".join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])
    _OTP_STORE[email] = {
        "otp":        otp,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS),
    }

    full_name = user.profile.full_name if user.profile else None

    # OTP email is sent synchronously — the user is waiting for the code.
    try:
        msg = _build_otp_email(email, otp, full_name)
        _send_raw(msg)
        logger.info("OTP sent to %s", email)
    except Exception as exc:
        logger.error("Failed to send OTP email to %s: %s", email, exc)
        return _bad(
            "We could not send the reset email right now. "
            "Please try again in a few minutes.",
            503,
        )

    return jsonify({"message": SUCCESS_MSG}), 200


@reset_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    """
    POST /auth/verify-otp
    Body: { email, otp }
    Returns: { reset_token } on success.
    """
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    otp   = (data.get("otp")   or "").strip()

    if not email or not otp:
        return _bad("Email and OTP are required.")

    record  = _OTP_STORE.get(email)
    INVALID = "The code is invalid or has expired. Request a new one."

    if not record:
        return _bad(INVALID, 400)

    if datetime.now(timezone.utc) > record["expires_at"]:
        _OTP_STORE.pop(email, None)
        return _bad(INVALID, 400)

    if not secrets.compare_digest(record["otp"], otp):
        return _bad(INVALID, 400)

    _OTP_STORE.pop(email, None)   # one-time use

    reset_token = _make_reset_token(email)
    logger.info("OTP verified for %s; reset_token issued", email)

    return jsonify({
        "message":     "Code verified. You may now set a new password.",
        "reset_token": reset_token,
    }), 200


@reset_bp.route("/reset-password", methods=["POST"])
def reset_password():
    """
    POST /auth/reset-password
    Body: { reset_token, password }
    Verifies the token, validates the new password, saves it, and sends a
    password-changed confirmation email in the background.
    """
    data         = request.get_json(silent=True) or {}
    reset_token  = (data.get("reset_token") or "").strip()
    new_password =  data.get("password")    or ""

    if not reset_token or not new_password:
        return _bad("reset_token and password are required.")

    email = _decode_reset_token(reset_token)
    if not email:
        return _bad(
            "The reset link has expired or is invalid. Please restart the process.",
            400,
        )

    user = User.query.filter_by(email=email).first()
    if not user:
        return _bad("Account not found.", 404)

    pw_err = _validate_password(new_password)
    if pw_err:
        return _bad(pw_err)

    if check_password_hash(user.password, new_password):
        return _bad("New password must be different from your current password.")

    user.password = generate_password_hash(new_password)
    db.session.commit()
    logger.info("Password reset completed for %s", email)

    # Confirmation email in background — never blocks the response
    full_name = user.profile.full_name if user.profile else None
    _fire_email(send_password_changed_email, email, full_name)

    return jsonify({"message": "Password reset successfully. You can now log in."}), 200