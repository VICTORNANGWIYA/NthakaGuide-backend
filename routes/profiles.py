import re
import logging

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, Profile, User

logger = logging.getLogger("NthakaGuide.profiles")

profiles_bp = Blueprint("profiles", __name__, url_prefix="/profiles")


# ── Reusable validators (same rules as auth.py) ────────────────────────────────

def _validate_phone(phone: str) -> str | None:
    """
    Malawi phone: +265 followed by exactly 9 digits starting with 8 or 9.
    Returns error string or None if valid / empty.
    """
    if not phone:
        return None  # optional field

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
    """
    Full name rules:
      • At least 2 characters
      • Must start with a letter
      • May include letters, numbers, spaces, hyphens, apostrophes, dots
      • Cannot be digits-only
    """
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
    """GET /profiles/ — returns the current user's profile."""
    user_id = get_jwt_identity()
    profile = Profile.query.filter_by(user_id=user_id).first()

    if not profile:
        return jsonify({"error": "Profile not found."}), 404

    return jsonify(profile.to_dict())


# ── PUT /profiles/ ─────────────────────────────────────────────────────────────
@profiles_bp.route("/", methods=["PUT"])
@jwt_required()
def upsert_profile():
    """
    PUT /profiles/
    Body (all fields optional):
        full_name   str — letters + optional numbers, cannot be digits-only
        phone       str — +265 followed by 9 digits starting with 8 or 9
        district    str — any string (validated as a known Malawi district on the frontend)
        avatar_url  str — any URL string (no deep URL validation needed here)

    Creates a profile if one does not exist; updates provided fields otherwise.
    Fields not included in the body are left unchanged.
    """
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    # ── Validate any provided fields before touching the DB ───────────────────
    if "full_name" in data:
        name_err = _validate_full_name(str(data["full_name"]))
        if name_err:
            return _bad(name_err)

    if "phone" in data and data["phone"]:
        phone_err = _validate_phone(str(data["phone"]))
        if phone_err:
            return _bad(phone_err)
        # Normalise: strip spaces before storage
        data["phone"] = str(data["phone"]).replace(" ", "")

    # ── Upsert ────────────────────────────────────────────────────────────────
    profile = Profile.query.filter_by(user_id=user_id).first()

    if not profile:
        # Ensure the user actually exists before creating a profile
        User.query.get_or_404(user_id)
        profile = Profile(user_id=user_id)
        db.session.add(profile)
        logger.info("Creating profile for user %s", user_id)

    updatable = ["full_name", "phone", "district", "avatar_url"]
    for field in updatable:
        if field in data:
            # Allow explicit null to clear a field
            setattr(profile, field, data[field] or None)

    db.session.commit()

    logger.info("Profile updated for user %s", user_id)
    return jsonify({"message": "Profile updated.", "profile": profile.to_dict()})


# ── DELETE /profiles/ ─────────────────────────────────────────────────────────
@profiles_bp.route("/", methods=["DELETE"])
@jwt_required()
def delete_profile():
    """DELETE /profiles/ — removes the user's profile (not the account)."""
    user_id = get_jwt_identity()
    profile = Profile.query.filter_by(user_id=user_id).first()

    if not profile:
        return jsonify({"error": "No profile to delete."}), 404

    db.session.delete(profile)
    db.session.commit()

    logger.info("Profile deleted for user %s", user_id)
    return jsonify({"message": "Profile deleted."})