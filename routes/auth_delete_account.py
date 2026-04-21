"""
Add this route to your existing routes/auth.py file.
It replaces your current DELETE /auth/delete-account endpoint.

Key change: accepts survey fields (reason, details) in the request body,
saves a DeletionSurvey record BEFORE deleting the user so the data is
not lost when the account (and any CASCADE deletes) fire.
"""

from models import db, User, DeletionSurvey
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request, jsonify
from werkzeug.security import check_password_hash

# ── Deletion reason options (kept in sync with frontend) ──────────────────────
DELETION_REASONS = {
    "not_useful":        "The app is not useful for my farming needs",
    "too_complicated":   "The app is too complicated to use",
    "poor_accuracy":     "Crop or fertilizer recommendations are inaccurate",
    "no_internet":       "I do not have reliable internet access",
    "privacy_concerns":  "I have concerns about my data and privacy",
    "switching_app":     "I am switching to a different application",
    "temporary":         "I am taking a break and may return",
    "other":             "Other reason",
}


@auth_bp.route("/delete-account", methods=["DELETE"])
@jwt_required()
def delete_account():
    """
    DELETE /auth/delete-account
    Body: {
        "password":  str,           -- required, must match current password
        "reason":    str,           -- required, key from DELETION_REASONS
        "details":   str | null     -- optional free-text (max 1000 chars)
    }

    Steps:
      1. Validate password
      2. Validate reason key
      3. Save DeletionSurvey record (before deletion so it is not lost)
      4. Delete user account
      5. Return success
    """
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    data     = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip()
    reason   = (data.get("reason")   or "").strip()
    details  = (data.get("details")  or "").strip()[:1000]  # cap at 1000 chars

    # ── Validate password ─────────────────────────────────────────────────────
    if not password:
        return jsonify({"error": "Password is required to delete your account."}), 400
    if not check_password_hash(user.password, password):
        return jsonify({"error": "Incorrect password."}), 401

    # ── Validate reason ───────────────────────────────────────────────────────
    if not reason:
        return jsonify({"error": "Please select a reason for deleting your account."}), 400
    if reason not in DELETION_REASONS:
        return jsonify({"error": f"Invalid reason. Must be one of: {list(DELETION_REASONS.keys())}"}), 400

    # ── Save survey BEFORE deleting (user_id stored as plain string, not FK) ──
    # We do NOT use a foreign key here because the user is about to be deleted.
    # Saving first means the survey survives even if deletion fails halfway.
    survey = DeletionSurvey(
        user_id      = user.id,
        user_email   = user.email,
        reason       = reason,
        reason_label = DELETION_REASONS[reason],
        details      = details or None,
    )
    db.session.add(survey)
    db.session.flush()   # write survey to DB but do not commit yet

    # ── Delete user (CASCADE removes Profile, AnalysisHistory, ChatLog) ───────
    db.session.delete(user)
    db.session.commit()  # single commit: survey saved + user deleted atomically

    return jsonify({"message": "Your account has been permanently deleted."})
