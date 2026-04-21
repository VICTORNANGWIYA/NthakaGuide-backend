"""
routes/admin_extended.py
────────────────────────
Extended admin endpoints for NthakaGuide.

CHANGES FROM PREVIOUS VERSION:
  - _AUDIT_LOG in-memory list REMOVED — all audit entries now written to
    the AuditLog database table so they survive restarts and are visible
    to every admin, not just the one who triggered the action.
  - _audit() helper writes to DB instead of a Python list.
  - GET /admin/logs now queries AuditLog from the DB with pagination,
    search, and optional action-type filter.
  - GET /admin/export/audit-log added — download full audit trail as CSV.
  - GET /admin/deletion-surveys added — admins can view all deletion
    survey responses collected when users delete their accounts.
  - GET /admin/export/deletion-surveys added — download as CSV.

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

from models import db, User, Profile, AnalysisHistory, AuditLog, DeletionSurvey
from routes.auth_reset import send_account_deactivated_email, send_account_reactivated_email

logger       = logging.getLogger("NthakaGuide.admin_ext")
admin_ext_bp = Blueprint("admin_ext", __name__, url_prefix="/admin")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Auth guard ─────────────────────────────────────────────────────────────────
def _require_admin():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user or user.role != "admin":
        return None, (jsonify({"error": "Admin access required."}), 403)
    return user, None


# ── Persistent audit helper ────────────────────────────────────────────────────
def _audit(
    admin_id: str,
    action: str,
    target_id: str = "",
    target_label: str = "",
    detail: str = "",
) -> None:
    """
    Write an audit entry to the AuditLog table.

    This replaces the old in-memory _AUDIT_LOG list. Every entry now
    persists across server restarts and is visible to all admins.

    IP address is captured from the request context when available.
    """
    try:
        ip = request.remote_addr if request else None
        entry = AuditLog(
            admin_id     = admin_id or None,
            action       = action,
            target_id    = target_id   or None,
            target_label = target_label or None,
            detail       = detail      or None,
            ip_address   = ip,
        )
        db.session.add(entry)
        db.session.commit()
        logger.info(
            "AUDIT  admin=%s  action=%s  target=%s  %s",
            admin_id, action, target_label or target_id, detail,
        )
    except Exception as exc:
        logger.error("Failed to write audit log entry: %s", exc)
        db.session.rollback()


# ─────────────────────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────────────────────
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


# ══════════════════════════════════════════════════════════════════════════════
#  USER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/users/<string:user_id>/deactivate", methods=["PUT"])
@jwt_required()
def deactivate_user(user_id: str):
    admin, err = _require_admin()
    if err: return err
    if user_id == admin.id:
        return jsonify({"error": "Cannot deactivate your own account."}), 400

    u = User.query.get_or_404(user_id)
    u.is_active = False
    db.session.commit()
    p = Profile.query.filter_by(user_id=u.id).first()
    send_account_deactivated_email(u.email, p.full_name if p else None)
    _audit(admin.id, "deactivate_user", user_id, u.email)
    return jsonify({"message": f"User {u.email} deactivated."})


@admin_ext_bp.route("/users/<string:user_id>/activate", methods=["PUT"])
@jwt_required()
def activate_user(user_id: str):
    admin, err = _require_admin()
    if err: return err

    u = User.query.get_or_404(user_id)
    u.is_active = True
    db.session.commit()
    p = Profile.query.filter_by(user_id=u.id).first()
    send_account_reactivated_email(u.email, p.full_name if p else None)
    _audit(admin.id, "activate_user", user_id, u.email)
    return jsonify({"message": f"User {u.email} activated."})


@admin_ext_bp.route("/users/<string:user_id>/promote", methods=["PUT"])
@jwt_required()
def promote_user(user_id: str):
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
#  DELETION SURVEYS
#  Populated by POST /auth/delete-account (see auth route below).
#  Admins read these here to understand why users are leaving.
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/deletion-surveys", methods=["GET"])
@jwt_required()
def deletion_surveys():
    """
    GET /admin/deletion-surveys
    Returns paginated deletion survey responses so admins can understand
    why users are leaving and prioritise improvements accordingly.
    """
    _, err = _require_admin()
    if err: return err

    page     = request.args.get("page",     1,  type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    pagination = (
        DeletionSurvey.query
        .order_by(DeletionSurvey.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Aggregate reason counts for summary
    reason_counts = (
        db.session.query(
            DeletionSurvey.reason_label,
            func.count().label("count"),
        )
        .group_by(DeletionSurvey.reason_label)
        .order_by(func.count().desc())
        .all()
    )

    return jsonify({
        "items":         [s.to_dict() for s in pagination.items],
        "total":         pagination.total,
        "page":          pagination.page,
        "pages":         pagination.pages,
        "per_page":      pagination.per_page,
        "reason_summary": [
            {"reason": r.reason_label, "count": r.count}
            for r in reason_counts
        ],
    })


@admin_ext_bp.route("/export/deletion-surveys", methods=["GET"])
@jwt_required()
def export_deletion_surveys():
    """GET /admin/export/deletion-surveys — download all survey responses as CSV."""
    admin, err = _require_admin()
    if err: return err

    surveys = DeletionSurvey.query.order_by(DeletionSurvey.created_at.desc()).all()
    rows    = [s.to_dict() for s in surveys]
    _audit(admin.id, "export_deletion_surveys", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_deletion_surveys_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


# ══════════════════════════════════════════════════════════════════════════════
#  AUDIT LOGS  (persistent DB — replaces in-memory _AUDIT_LOG)
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/logs", methods=["GET"])
@jwt_required()
def get_logs():
    """
    GET /admin/logs
    Query params: page, per_page, action (filter by action type), search (admin email)

    Now reads from the AuditLog DB table instead of the in-memory list.
    This means:
      - Logs persist across server restarts
      - All admins see ALL admin actions, not just their own session
      - Logs are paginated and filterable
    """
    _, err = _require_admin()
    if err: return err

    page     = request.args.get("page",     1,  type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    action   = request.args.get("action",   "").strip()
    search   = request.args.get("search",   "").strip()

    query = AuditLog.query

    if action:
        query = query.filter(AuditLog.action == action)

    if search:
        # Search by admin email via join
        query = (
            query
            .join(User, AuditLog.admin_id == User.id, isouter=True)
            .filter(User.email.ilike(f"%{search}%"))
        )

    pagination = (
        query
        .order_by(AuditLog.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Distinct action types for filter dropdown in frontend
    action_types = [
        row[0] for row in
        db.session.query(func.distinct(AuditLog.action))
        .order_by(AuditLog.action)
        .all()
    ]

    return jsonify({
        "items":        [log.to_dict() for log in pagination.items],
        "total":        pagination.total,
        "page":         pagination.page,
        "pages":        pagination.pages,
        "per_page":     pagination.per_page,
        "action_types": action_types,
    })


@admin_ext_bp.route("/export/audit-log", methods=["GET"])
@jwt_required()
def export_audit_log():
    """GET /admin/export/audit-log — download full audit trail as CSV."""
    admin, err = _require_admin()
    if err: return err

    logs  = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    rows  = [l.to_dict() for l in logs]
    _audit(admin.id, "export_audit_log", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_audit_log_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


# ══════════════════════════════════════════════════════════════════════════════
#  ADVANCED SEARCH
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/analyses/search", methods=["GET"])
@jwt_required()
def search_analyses():
    _, err = _require_admin()
    if err: return err

    page      = request.args.get("page",      1,  type=int)
    per_page  = min(request.args.get("per_page", 20, type=int), 100)
    district  = request.args.get("district",  "").strip()
    crop      = request.args.get("crop",      "").strip()
    mode      = request.args.get("mode",      "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to   = request.args.get("date_to",   "").strip()
    search    = request.args.get("search",    "").strip()

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

@admin_ext_bp.route("/export/analyses", methods=["GET"])
@jwt_required()
def export_analyses():
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
            "climate_zone":     a.climate_zone     or "",
            "input_mode":       a.input_mode        or "",
            "recommended_crop": a.recommended_crop,
            "crop_score":       a.crop_score        or "",
            "crop_confidence":  a.crop_confidence   or "",
            "fertilizer_type":  a.fertilizer_type   or "",
            "ph":               a.ph                or "",
            "nitrogen":         a.nitrogen          or "",
            "phosphorus":       a.phosphorus        or "",
            "potassium":        a.potassium         or "",
            "rainfall_mm":      a.rainfall_mm       or "",
            "created_at":       a.created_at.isoformat(),
        })

    _audit(admin.id, "export_analyses", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_analyses_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


@admin_ext_bp.route("/export/users", methods=["GET"])
@jwt_required()
def export_users():
    admin, err = _require_admin()
    if err: return err

    users = User.query.filter_by(role="user").order_by(User.created_at.desc()).all()
    rows  = []
    for u in users:
        p     = Profile.query.filter_by(user_id=u.id).first()
        count = AnalysisHistory.query.filter_by(user_id=u.id).count()
        rows.append({
            "id":        u.id,
            "email":     u.email,
            "full_name": p.full_name if p else "",
            "phone":     p.phone     if p else "",
            "district":  p.district  if p else "",
            "is_active": u.is_active,
            "analyses":  count,
            "joined":    u.created_at.isoformat(),
        })

    _audit(admin.id, "export_users", "", f"{len(rows)} rows")
    fname = f"nthakaGuide_users_{datetime.now().strftime('%Y%m%d')}.csv"
    return _csv_response(rows, fname)


@admin_ext_bp.route("/export/monthly-report", methods=["GET"])
@jwt_required()
def export_monthly_report():
    admin, err = _require_admin()
    if err: return err

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)

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
#  SYSTEM ALERTS
# ══════════════════════════════════════════════════════════════════════════════

@admin_ext_bp.route("/alerts", methods=["GET"])
@jwt_required()
def get_alerts():
    _, err = _require_admin()
    if err: return err

    alerts = []
    now    = datetime.now(timezone.utc)

    yesterday   = now - timedelta(days=1)
    two_days    = now - timedelta(days=2)
    today_count     = AnalysisHistory.query.filter(AnalysisHistory.created_at >= yesterday).count()
    yesterday_count = AnalysisHistory.query.filter(
        AnalysisHistory.created_at >= two_days,
        AnalysisHistory.created_at < yesterday,
    ).count()
    if yesterday_count > 0 and today_count > yesterday_count * 1.5:
        alerts.append({
            "level":     "info",
            "title":     "Analysis Activity Spike",
            "message":   f"Today's analyses ({today_count}) are {round((today_count/yesterday_count-1)*100)}% above yesterday ({yesterday_count}).",
            "timestamp": now.isoformat(),
        })

    thirty_days_ago = now - timedelta(days=30)
    active_30 = (
        db.session.query(func.count(func.distinct(AnalysisHistory.district)))
        .filter(AnalysisHistory.created_at >= thirty_days_ago)
        .scalar() or 0
    )
    inactive = 28 - active_30
    if inactive > 5:
        alerts.append({
            "level":     "warning",
            "title":     "Low District Coverage",
            "message":   f"{inactive} of 28 districts have had no analyses in the past 30 days.",
            "timestamp": now.isoformat(),
        })

    deactivated = User.query.filter_by(is_active=False, role="user").count()
    if deactivated > 0:
        alerts.append({
            "level":     "info",
            "title":     "Deactivated Accounts",
            "message":   f"{deactivated} user account(s) are currently deactivated.",
            "timestamp": now.isoformat(),
        })

    model_dir      = os.path.join(BASE, "models")
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

    two_days_ago = now - timedelta(hours=48)
    recent = AnalysisHistory.query.filter(AnalysisHistory.created_at >= two_days_ago).count()
    if recent == 0:
        alerts.append({
            "level":     "warning",
            "title":     "No Recent Activity",
            "message":   "No analyses have been submitted in the past 48 hours.",
            "timestamp": now.isoformat(),
        })

    # Alert if deletion survey responses exist (prompt admin to review)
    survey_count = DeletionSurvey.query.count()
    if survey_count > 0:
        unreviewed = DeletionSurvey.query.order_by(
            DeletionSurvey.created_at.desc()
        ).first()
        alerts.append({
            "level":     "info",
            "title":     f"Deletion Feedback — {survey_count} response(s)",
            "message":   f"Users have submitted {survey_count} account-deletion survey(s). Review them in the Surveys tab.",
            "timestamp": unreviewed.created_at.isoformat() if unreviewed else now.isoformat(),
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

_ACTIVE_MODEL = {"algorithm": "random_forest"}

AVAILABLE_MODELS = [
    {"id": "random_forest",     "label": "Random Forest",     "accuracy": "94.66%", "file": "best_crop_model.pkl"},
    {"id": "gradient_boosting", "label": "Gradient Boosting", "accuracy": "94.43%", "file": "gb_crop_model.pkl"},
    {"id": "decision_tree",     "label": "Decision Tree",     "accuracy": "91.98%", "file": "dt_crop_model.pkl"},
    {"id": "logistic_regression","label": "Logistic Regression","accuracy": "60.59%","file": "lr_crop_model.pkl"},
]


@admin_ext_bp.route("/model/status", methods=["GET"])
@jwt_required()
def model_status():
    _, err = _require_admin()
    if err: return err

    model_dir = os.path.join(BASE, "models")
    result = []
    for m in AVAILABLE_MODELS:
        path   = os.path.join(model_dir, m["file"])
        exists = os.path.exists(path)
        size   = f"{os.path.getsize(path) / 1024:.1f} KB" if exists else "—"
        result.append({**m, "present": exists, "size": size,
                        "active": m["id"] == _ACTIVE_MODEL["algorithm"]})
    return jsonify({"active_model": _ACTIVE_MODEL["algorithm"], "models": result})


@admin_ext_bp.route("/model/switch", methods=["PUT"])
@jwt_required()
def switch_model():
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
    _audit(admin.id, "switch_model", algo, algo, f"switched active model to {algo}")
    return jsonify({"message": f"Active model switched to {algo}.", "active_model": algo})


@admin_ext_bp.route("/model/training-info", methods=["GET"])
@jwt_required()
def training_info():
    _, err = _require_admin()
    if err: return err

    report_path = os.path.join(BASE, "models", "training_report.json")
    if os.path.exists(report_path):
        with open(report_path) as f:
            return jsonify(json.load(f))

    return jsonify({
        "algorithm":     _ACTIVE_MODEL["algorithm"],
        "trained_on":    "2025-01-15",
        "training_rows": 30499,
        "feature_count": 7,
        "features":      ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"],
        "classes":       41,
        "accuracy":      0.9466,
        "f1_score":      0.9469,
        "cv_mean":       0.8524,
        "note":          "training_report.json not found — showing defaults",
    })