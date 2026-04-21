import re
import base64
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, Profile, User

logger = logging.getLogger("NthakaGuide.profiles")

profiles_bp = Blueprint("profiles", __name__, url_prefix="/profiles")

# ── Allowed image MIME types ───────────────────────────────────────────────────
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_AVATAR_BYTES    = 2 * 1024 * 1024  # 2 MB decoded


# ── Reusable validators ────────────────────────────────────────────────────────

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
        return "The 9 digits after +265 must start with 8 or 9 (e.g. 88x, 99x)."
    return None


def _validate_full_name(name: str) -> str | None:
    if not name or not name.strip():
        return "Full name cannot be blank."
    name = name.strip()
    if len(name) < 2:
        return "Name must be at least 2 characters long."
    if re.fullmatch(r"\d+", name):
        return "Name cannot consist of numbers only."
    if not re.match(r"^[a-zA-Z]", name):
        return "Name must start with a letter."
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9 .\'\-]*", name):
        return (
            "Name may only contain letters, numbers, spaces, "
            "hyphens (-), apostrophes ('), and dots (.)."
        )
    return None


def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


# ── GET /profiles/ ─────────────────────────────────────────────────────────────
@profiles_bp.route("/", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    profile = Profile.query.filter_by(user_id=user_id).first()
    if not profile:
        return jsonify({"error": "Profile not found."}), 404
    return jsonify(profile.to_dict())


# ── PUT /profiles/ ─────────────────────────────────────────────────────────────
@profiles_bp.route("/", methods=["PUT"])
@jwt_required()
def upsert_profile():
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    if "full_name" in data:
        name_err = _validate_full_name(str(data["full_name"]))
        if name_err:
            return _bad(name_err)

    if "phone" in data and data["phone"]:
        phone_err = _validate_phone(str(data["phone"]))
        if phone_err:
            return _bad(phone_err)
        data["phone"] = str(data["phone"]).replace(" ", "")

    profile = Profile.query.filter_by(user_id=user_id).first()
    if not profile:
        User.query.get_or_404(user_id)
        profile = Profile(user_id=user_id)
        db.session.add(profile)
        logger.info("Creating profile for user %s", user_id)

    updatable = ["full_name", "phone", "district", "avatar_url"]
    for field in updatable:
        if field in data:
            setattr(profile, field, data[field] or None)

    db.session.commit()
    logger.info("Profile updated for user %s", user_id)
    return jsonify({"message": "Profile updated.", "profile": profile.to_dict()})


# ── POST /profiles/avatar ──────────────────────────────────────────────────────
@profiles_bp.route("/avatar", methods=["POST"])
@jwt_required()
def upload_avatar():
    """
    POST /profiles/avatar
    Body: { "avatar": "<data URL or raw base64>", "mime_type": "image/jpeg" }

    Accepts a base64-encoded image (with or without a data-URL prefix).
    Validates MIME type and size, then stores the full data URL in
    profile.avatar_url.  Returns the updated profile dict.
    """
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    avatar_raw = (data.get("avatar") or "").strip()
    if not avatar_raw:
        return _bad("No avatar data provided.")

    # ── Parse data URL or raw base64 ─────────────────────────────────────────
    if avatar_raw.startswith("data:"):
        # data:<mime>;base64,<data>
        try:
            header, b64_data = avatar_raw.split(",", 1)
            mime_type = header.split(":")[1].split(";")[0].strip().lower()
        except (ValueError, IndexError):
            return _bad("Invalid data URL format.")
    else:
        # Raw base64 — caller must supply mime_type separately
        mime_type = (data.get("mime_type") or "").strip().lower()
        b64_data  = avatar_raw

    if mime_type not in _ALLOWED_IMAGE_TYPES:
        return _bad(
            f"Unsupported image type '{mime_type}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_IMAGE_TYPES))}."
        )

    # ── Validate base64 and size ──────────────────────────────────────────────
    try:
        decoded = base64.b64decode(b64_data, validate=True)
    except Exception:
        return _bad("Avatar data is not valid base64.")

    if len(decoded) > _MAX_AVATAR_BYTES:
        mb = _MAX_AVATAR_BYTES // (1024 * 1024)
        return _bad(f"Image is too large. Maximum size is {mb} MB.")

    # ── Upsert profile with new avatar URL ───────────────────────────────────
    profile = Profile.query.filter_by(user_id=user_id).first()
    if not profile:
        User.query.get_or_404(user_id)
        profile = Profile(user_id=user_id)
        db.session.add(profile)

    profile.avatar_url = f"data:{mime_type};base64,{b64_data}"
    db.session.commit()

    logger.info("Avatar updated for user %s (%s, %d bytes)", user_id, mime_type, len(decoded))
    return jsonify({"message": "Avatar updated.", "profile": profile.to_dict()})


# ── DELETE /profiles/avatar ────────────────────────────────────────────────────
@profiles_bp.route("/avatar", methods=["DELETE"])
@jwt_required()
def delete_avatar():
    """DELETE /profiles/avatar — removes the stored avatar."""
    user_id = get_jwt_identity()
    profile = Profile.query.filter_by(user_id=user_id).first()
    if not profile:
        return _bad("Profile not found.", 404)

    profile.avatar_url = None
    db.session.commit()
    logger.info("Avatar removed for user %s", user_id)
    return jsonify({"message": "Avatar removed.", "profile": profile.to_dict()})


# ── DELETE /profiles/ ─────────────────────────────────────────────────────────
@profiles_bp.route("/", methods=["DELETE"])
@jwt_required()
def delete_profile():
    user_id = get_jwt_identity()
    profile = Profile.query.filter_by(user_id=user_id).first()
    if not profile:
        return jsonify({"error": "No profile to delete."}), 404
    db.session.delete(profile)
    db.session.commit()
    logger.info("Profile deleted for user %s", user_id)
    return jsonify({"message": "Profile deleted."})