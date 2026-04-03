"""
routes/admin_extended.py
────────────────────────
Extended admin endpoints for NthakaGuide:
  • User management  (ban / activate / promote / delete / reset-password)
  • CSV/Excel export (analyses, users, monthly report)
  • Activity logs    (audit trail of admin actions)
  • System alerts    (API health, failed logins, model status)
  • Model control    (switch active model, view training metadata)
  • Advanced search  (date range, district, crop, mode filters)

All routes require JWT + role == "admin".
"""

import csv
import io
import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from models import db, User, Profile, AnalysisHistory

logger      = logging.getLogger("soilsense.admin_ext")
admin_ext_bp = Blueprint("admin_ext", __name__, url_prefix="/admin")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Auth guard ─────────────────────────────────────────────────────────────────
def _require_admin():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user or user.role != "admin":
        return None, (jsonify({"error": "Admin access required."}), 403)
    return user, None


# ── Audit log helper ───────────────────────────────────────────────────────────
_AUDIT_LOG: list[dict] = []   # in-memory for now; swap for DB table in production

def _audit(admin_id: str, action: str, target: str = "", detail: str = ""):
    _AUDIT_LOG.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "admin_id":  admin_id,
        "action":    action,
        "target":    target,
        "detail":    detail,
    })
    logger.info("AUDIT  admin=%s  action=%s  target=%s  %s", admin_id, action, target, detail)


# ══════════════════════════════════════════════════════════════════════════════
#  USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/users/<string:user_id>/deactivate", methods=["PUT"])
@jwt_required()
def deactivate_user(user_id: str):
    """Disable a user account (is_active = False)."""
    admin, err = _require_admin()
    if err: return err
    if user_id == admin.id:
        return jsonify({"error": "Cannot deactivate your own account."}), 400

    u = User.query.get_or_404(user_id)
    u.is_active = False
    db.session.commit()
    _audit(admin.id, "deactivate_user", user_id, u.email)
    return jsonify({"message": f"User {u.email} deactivated."})


@admin_ext_bp.route("/users/<string:user_id>/activate", methods=["PUT"])
@jwt_required()
def activate_user(user_id: str):
    """Re-enable a deactivated user account."""
    admin, err = _require_admin()
    if err: return err

    u = User.query.get_or_404(user_id)
    u.is_active = True
    db.session.commit()
    _audit(admin.id, "activate_user", user_id, u.email)
    return jsonify({"message": f"User {u.email} activated."})


@admin_ext_bp.route("/users/<string:user_id>/promote", methods=["PUT"])
@jwt_required()
def promote_user(user_id: str):
    """Promote a regular user to admin (subject to MAX_ADMIN_ACCOUNTS cap)."""
    from routes.auth import MAX_ADMIN_ACCOUNTS, _admin_count
    admin, err = _require_admin()
    if err: return err

    u = User.query.get_or_404(user_id)
    if u.role == "admin":
        return jsonify({"error": "User is already an admin."}), 400
    if _admin_count() >= MAX_ADMIN_ACCOUNTS:
        return jsonify({"error": f"Max admin limit ({MAX_ADMIN_ACCOUNTS}) reached."}), 403

    u.role = "admin"
    db.session.commit()
    _audit(admin.id, "promote_user", user_id, u.email)
    return jsonify({"message": f"{u.email} promoted to admin."})


@admin_ext_bp.route("/users/<string:user_id>/demote", methods=["PUT"])
@jwt_required()
def demote_user(user_id: str):
    """Demote an admin back to regular user."""
    admin, err = _require_admin()
    if err: return err
    if user_id == admin.id:
        return jsonify({"error": "Cannot demote yourself."}), 400

    u = User.query.get_or_404(user_id)
    if u.role != "admin":
        return jsonify({"error": "User is not an admin."}), 400
    u.role = "user"
    db.session.commit()
    _audit(admin.id, "demote_user", user_id, u.email)
    return jsonify({"message": f"{u.email} demoted to regular user."})


@admin_ext_bp.route("/users/<string:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id: str):
    """Permanently delete a user and all their data."""
    admin, err = _require_admin()
    if err: return err
    if user_id == admin.id:
        return jsonify({"error": "Cannot delete your own account."}), 400

    u = User.query.get_or_404(user_id)
    email = u.email
    db.session.delete(u)
    db.session.commit()
    _audit(admin.id, "delete_user", user_id, email)
    return jsonify({"message": f"User {email} deleted."})


@admin_ext_bp.route("/users/<string:user_id>/reset-password", methods=["PUT"])
@jwt_required()
def reset_password(user_id: str):
    """
    PUT /admin/users/<id>/reset-password
    Body: { "new_password": str }
    Admin sets a new password directly (no old password needed).
    """
    from routes.auth import _validate_password
    admin, err = _require_admin()
    if err: return err

    data   = request.get_json(silent=True) or {}
    new_pw = data.get("new_password") or ""

    pw_err = _validate_password(new_pw)
    if pw_err:
        return jsonify({"error": pw_err}), 400

    u = User.query.get_or_404(user_id)
    u.password = generate_password_hash(new_pw)
    db.session.commit()
    _audit(admin.id, "reset_password", user_id, u.email)
    return jsonify({"message": f"Password reset for {u.email}."})


# ══════════════════════════════════════════════════════════════════════════════
#  ADVANCED SEARCH / FILTER
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/analyses/search", methods=["GET"])
@jwt_required()
def search_analyses():
    """
    GET /admin/analyses/search
    Query params: district, crop, mode, date_from (YYYY-MM-DD), date_to, page, per_page
    """
    _, err = _require_admin()
    if err: return err

    page       = request.args.get("page",      1,  type=int)
    per_page   = min(request.args.get("per_page", 20, type=int), 100)
    district   = request.args.get("district",  "").strip()
    crop       = request.args.get("crop",      "").strip()
    mode       = request.args.get("mode",      "").strip()
    date_from  = request.args.get("date_from", "").strip()
    date_to    = request.args.get("date_to",   "").strip()
    search     = request.args.get("search",    "").strip()

    query = AnalysisHistory.query

    if district:
        query = query.filter(AnalysisHistory.district.ilike(f"%{district}%"))
    if crop:
        query = query.filter(AnalysisHistory.recommended_crop.ilike(f"%{crop}%"))
    if mode:
        query = query.filter(AnalysisHistory.input_mode == mode)
    if search:
        like = f"%{search}%"
        query = query.filter(
            AnalysisHistory.district.ilike(like)
            | AnalysisHistory.recommended_crop.ilike(like)
        )
    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(AnalysisHistory.created_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            query = query.filter(AnalysisHistory.created_at < dt)
        except ValueError:
            pass

    pagination = (
        query.order_by(AnalysisHistory.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    items = []
    for a in pagination.items:
        d = a.to_dict(include_full=False)
        u = User.query.get(a.user_id)
        p = Profile.query.filter_by(user_id=a.user_id).first()
        d["user_email"] = u.email      if u else "—"
        d["user_name"]  = (p.full_name if p and p.full_name else (u.email if u else "—"))
        items.append(d)

    return jsonify({
        "items":    items,
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT / REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def _csv_response(rows: list[dict], filename: str):
    if not rows:
        return jsonify({"error": "No data to export."}), 404
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    resp = make_response(output.getvalue())
    resp.headers["Content-Type"]        = "text/csv"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@admin_ext_bp.route("/export/analyses", methods=["GET"])
@jwt_required()
def export_analyses():
    """GET /admin/export/analyses  — download all analyses as CSV."""
    admin, err = _require_admin()
    if err: return err

    district  = request.args.get("district",  "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to",   "").strip()

    query = AnalysisHistory.query
    if district:
        query = query.filter(AnalysisHistory.district.ilike(f"%{district}%"))
    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            query = query.filter(AnalysisHistory.created_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
            query = query.filter(AnalysisHistory.created_at < dt)
        except ValueError:
            pass

    records = query.order_by(AnalysisHistory.created_at.desc()).all()
    rows = []
    for a in records:
        u = User.query.get(a.user_id)
        p = Profile.query.filter_by(user_id=a.user_id).first()
        rows.append({
            "id":               a.id,
            "user_email":       u.email      if u else "",
            "user_name":        p.full_name  if p and p.full_name else "",
            "district":         a.district,
            "climate_zone":     a.climate_zone or "",
            "input_mode":       a.input_mode or "",
            "recommended_crop": a.recommended_crop,
            "crop_score":       a.crop_score or "",
            "crop_confidence":  a.crop_confidence or "",
            "fertilizer_type":  a.fertilizer_type or "",
            "yield_predicted":  a.yield_predicted or "",
            "yield_category":   a.yield_category or "",
            "pest_risk_level":  a.pest_risk_level or "",
            "ph":               a.ph or "",
            "nitrogen":         a.nitrogen or "",
            "phosphorus":       a.phosphorus or "",
            "potassium":        a.potassium or "",
            "rainfall_mm":      a.rainfall_mm or "",
            "created_at":       a.created_at.isoformat(),
        })

    _audit(admin.id, "export_analyses", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_analyses_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


@admin_ext_bp.route("/export/users", methods=["GET"])
@jwt_required()
def export_users():
    """GET /admin/export/users  — download all users as CSV."""
    admin, err = _require_admin()
    if err: return err

    users = User.query.filter_by(role="user").order_by(User.created_at.desc()).all()
    rows  = []
    for u in users:
        p     = Profile.query.filter_by(user_id=u.id).first()
        count = AnalysisHistory.query.filter_by(user_id=u.id).count()
        rows.append({
            "id":         u.id,
            "email":      u.email,
            "full_name":  p.full_name  if p else "",
            "phone":      p.phone      if p else "",
            "district":   p.district   if p else "",
            "is_active":  u.is_active,
            "analyses":   count,
            "joined":     u.created_at.isoformat(),
        })

    _audit(admin.id, "export_users", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_users_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


@admin_ext_bp.route("/export/monthly-report", methods=["GET"])
@jwt_required()
def export_monthly_report():
    """
    GET /admin/export/monthly-report  — last 12 months summary CSV.
    FIX: Uses Python-side grouping instead of func.strftime which is
    SQLite-only and fails on PostgreSQL and other databases.
    """
    admin, err = _require_admin()
    if err: return err

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)

    # Fetch timestamps + user_id + district in one query
    records = (
        AnalysisHistory.query
        .filter(AnalysisHistory.created_at >= cutoff)
        .with_entities(
            AnalysisHistory.created_at,
            AnalysisHistory.user_id,
            AnalysisHistory.district,
        )
        .all()
    )

    # Group by "YYYY-MM" in Python
    month_data: dict[str, dict] = defaultdict(lambda: {
        "analyses":     0,
        "unique_users": set(),
        "districts":    set(),
    })

    for (ts, user_id, district) in records:
        if ts is None:
            continue
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        key = ts.strftime("%Y-%m")
        month_data[key]["analyses"]     += 1
        month_data[key]["unique_users"].add(user_id)
        month_data[key]["districts"].add(district)

    rows = []
    for ym in sorted(month_data.keys()):
        d = month_data[ym]
        rows.append({
            "month":        ym,
            "analyses":     d["analyses"],
            "unique_users": len(d["unique_users"]),
            "districts":    len(d["districts"]),
        })

    _audit(admin.id, "export_monthly_report", "", f"{len(rows)} months")
    fname = f"nthakaGuide_monthly_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


# ══════════════════════════════════════════════════════════════════════════════
#  ACTIVITY LOGS / AUDIT TRAIL
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/logs", methods=["GET"])
@jwt_required()
def get_logs():
    """GET /admin/logs  — most recent audit log entries (newest first)."""
    _, err = _require_admin()
    if err: return err

    page     = request.args.get("page",     1,  type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    entries  = list(reversed(_AUDIT_LOG))
    start    = (page - 1) * per_page
    end      = start + per_page

    return jsonify({
        "items":    entries[start:end],
        "total":    len(entries),
        "page":     page,
        "per_page": per_page,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/alerts", methods=["GET"])
@jwt_required()
def get_alerts():
    """
    GET /admin/alerts  — auto-generated system alerts based on DB state.
    Returns a list of { level, title, message, timestamp }.
    """
    _, err = _require_admin()
    if err: return err

    alerts = []
    now    = datetime.now(timezone.utc)

    # 1. Check for analysis spike (>50% more than 24h average)
    yesterday = now - timedelta(days=1)
    two_days  = now - timedelta(days=2)
    today_count     = AnalysisHistory.query.filter(AnalysisHistory.created_at >= yesterday).count()
    yesterday_count = AnalysisHistory.query.filter(
        AnalysisHistory.created_at >= two_days,
        AnalysisHistory.created_at < yesterday
    ).count()
    if yesterday_count > 0 and today_count > yesterday_count * 1.5:
        alerts.append({
            "level":     "info",
            "title":     "Analysis Activity Spike",
            "message":   f"Today's analyses ({today_count}) are {round((today_count/yesterday_count-1)*100)}% above yesterday ({yesterday_count}).",
            "timestamp": now.isoformat(),
        })

    # 2. Check for inactive districts (no analyses in 30 days)
    thirty_days_ago = now - timedelta(days=30)
    active_30 = (
        db.session.query(func.count(func.distinct(AnalysisHistory.district)))
        .filter(AnalysisHistory.created_at >= thirty_days_ago)
        .scalar() or 0
    )
    total_districts = 28
    inactive = total_districts - active_30
    if inactive > 5:
        alerts.append({
            "level":     "warning",
            "title":     "Low District Coverage",
            "message":   f"{inactive} of {total_districts} districts have had no analyses in the past 30 days.",
            "timestamp": now.isoformat(),
        })

    # 3. Check for deactivated users
    deactivated = User.query.filter_by(is_active=False, role="user").count()
    if deactivated > 0:
        alerts.append({
            "level":     "info",
            "title":     "Deactivated Accounts",
            "message":   f"{deactivated} user account(s) are currently deactivated.",
            "timestamp": now.isoformat(),
        })

    # 4. Check model files
    model_dir    = os.path.join(BASE, "models")
    missing_models = [
        f for f in ["best_crop_model.pkl", "best_fert_model.pkl", "crop_scaler.pkl"]
        if not os.path.exists(os.path.join(model_dir, f))
    ]
    if missing_models:
        alerts.append({
            "level":     "error",
            "title":     "Missing Model Files",
            "message":   f"The following model files are missing: {', '.join(missing_models)}",
            "timestamp": now.isoformat(),
        })

    # 5. No analyses in 48 hours
    two_days_ago = now - timedelta(hours=48)
    recent = AnalysisHistory.query.filter(AnalysisHistory.created_at >= two_days_ago).count()
    if recent == 0:
        alerts.append({
            "level":     "warning",
            "title":     "No Recent Activity",
            "message":   "No analyses have been submitted in the past 48 hours.",
            "timestamp": now.isoformat(),
        })

    if not alerts:
        alerts.append({
            "level":     "success",
            "title":     "All Systems Normal",
            "message":   "No issues detected. System is operating normally.",
            "timestamp": now.isoformat(),
        })

    return jsonify(alerts)


# ══════════════════════════════════════════════════════════════════════════════
#  MODEL CONTROL
# ══════════════════════════════════════════════════════════════════════════════

# Track which algorithm is currently "active" (persisted in memory; use DB in prod)
_ACTIVE_MODEL = {"algorithm": "random_forest"}

AVAILABLE_MODELS = [
    {"id": "random_forest",    "label": "Random Forest",     "accuracy": "99.55%", "file": "best_crop_model.pkl"},
    {"id": "gradient_boosting","label": "Gradient Boosting", "accuracy": "98.18%", "file": "gb_crop_model.pkl"},
    {"id": "decision_tree",    "label": "Decision Tree",     "accuracy": "98.64%", "file": "dt_crop_model.pkl"},
    {"id": "naive_bayes",      "label": "Naive Bayes",       "accuracy": "99.49%", "file": "nb_crop_model.pkl"},
]


@admin_ext_bp.route("/model/status", methods=["GET"])
@jwt_required()
def model_status():
    """GET /admin/model/status — list models with file presence and active flag."""
    _, err = _require_admin()
    if err: return err

    model_dir = os.path.join(BASE, "models")
    result = []
    for m in AVAILABLE_MODELS:
        path   = os.path.join(model_dir, m["file"])
        exists = os.path.exists(path)
        size   = f"{os.path.getsize(path) / 1024:.1f} KB" if exists else "—"
        result.append({
            **m,
            "present": exists,
            "size":    size,
            "active":  m["id"] == _ACTIVE_MODEL["algorithm"],
        })
    return jsonify({
        "active_model": _ACTIVE_MODEL["algorithm"],
        "models":       result,
    })


@admin_ext_bp.route("/model/switch", methods=["PUT"])
@jwt_required()
def switch_model():
    """
    PUT /admin/model/switch
    Body: { "algorithm": "random_forest" | "gradient_boosting" | ... }
    """
    admin, err = _require_admin()
    if err: return err

    data  = request.get_json(silent=True) or {}
    algo  = data.get("algorithm", "").strip()
    valid = [m["id"] for m in AVAILABLE_MODELS]
    if algo not in valid:
        return jsonify({"error": f"Unknown algorithm. Choose from: {valid}"}), 400

    model_dir = os.path.join(BASE, "models")
    model_map = {m["id"]: m["file"] for m in AVAILABLE_MODELS}
    if not os.path.exists(os.path.join(model_dir, model_map[algo])):
        return jsonify({"error": f"Model file '{model_map[algo]}' not found on disk."}), 404

    _ACTIVE_MODEL["algorithm"] = algo
    _audit(admin.id, "switch_model", algo, f"switched active model to {algo}")
    logger.info("Active model switched to %s by admin %s", algo, admin.id)
    return jsonify({"message": f"Active model switched to {algo}.", "active_model": algo})


@admin_ext_bp.route("/model/training-info", methods=["GET"])
@jwt_required()
def training_info():
    """GET /admin/model/training-info — metadata about current model."""
    _, err = _require_admin()
    if err: return err

    # Read training_report.json if it exists, otherwise return static info
    report_path = os.path.join(BASE, "models", "training_report.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            return jsonify(json.load(f))

    # Fallback static metadata
    return jsonify({
        "algorithm":        _ACTIVE_MODEL["algorithm"],
        "trained_on":       "2025-01-15",
        "training_rows":    66341,
        "feature_count":    7,
        "features":         ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"],
        "classes":          28,
        "accuracy":         0.9955,
        "f1_score":         0.9954,
        "cv_mean":          0.9949,
        "note":             "training_report.json not found — showing defaults",
    })