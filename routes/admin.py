"""
routes/admin.py
───────────────
Admin-only API endpoints that power the AdminDashboard frontend.
All routes require a valid JWT where the resolved user has role == "admin".

Endpoints
─────────
GET  /admin/stats          → KPI summary (totals, uptime, coverage)
GET  /admin/analyses       → paginated analysis log with optional search
GET  /admin/users          → paginated user list with optional search
GET  /admin/districts      → per-district aggregated stats
GET  /admin/crops          → crop recommendation frequency table
GET  /admin/fertilizers    → fertilizer recommendation frequency table
GET  /admin/monthly        → analyses grouped by month (last 12 months)
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from models import db, User, Profile, AnalysisHistory

logger   = logging.getLogger("soilsense.admin")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Auth guard ─────────────────────────────────────────────────────────────────
def _require_admin():
    """
    Call at the top of every admin endpoint.
    Returns (user, None) on success or (None, error_response) on failure.
    """
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user or user.role != "admin":
        return None, (jsonify({"error": "Admin access required."}), 403)
    return user, None


# ── GET /admin/stats ───────────────────────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    _, err = _require_admin()
    if err:
        return err

    total_analyses = AnalysisHistory.query.count()
    total_users    = User.query.filter_by(role="user").count()
    total_admins   = User.query.filter_by(role="admin").count()

    # Active districts (distinct districts with at least 1 analysis)
    active_districts = (
        db.session.query(func.count(func.distinct(AnalysisHistory.district)))
        .scalar() or 0
    )

    # Analyses today
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    analyses_today = AnalysisHistory.query.filter(
        AnalysisHistory.created_at >= today_start
    ).count()

    # New users this week
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_week = User.query.filter(
        User.created_at >= week_start,
        User.role == "user",
    ).count()

    # Input mode breakdown
    mode_rows = (
        db.session.query(
            AnalysisHistory.input_mode,
            func.count(AnalysisHistory.input_mode).label("cnt"),
        )
        .group_by(AnalysisHistory.input_mode)
        .all()
    )
    mode_breakdown = {(r.input_mode or "lab"): r.cnt for r in mode_rows}

    return jsonify({
        "total_analyses":    total_analyses,
        "total_users":       total_users,
        "total_admins":      total_admins,
        "active_districts":  active_districts,
        "analyses_today":    analyses_today,
        "new_users_week":    new_users_week,
        "mode_breakdown":    mode_breakdown,
        "api_uptime":        "99.97%",   # static — integrate your monitor if needed
    })


# ── GET /admin/monthly ─────────────────────────────────────────────────────────
@admin_bp.route("/monthly", methods=["GET"])
@jwt_required()
def monthly():
    """
    Returns analyses count per month for the last 12 months.
    FIX: Uses Python-side grouping instead of func.strftime which is
    SQLite-only and fails on PostgreSQL and other databases.
    """
    _, err = _require_admin()
    if err:
        return err

    cutoff = datetime.now(timezone.utc) - timedelta(days=365)

    # Fetch only the created_at timestamps — avoids DB-specific date functions
    records = (
        AnalysisHistory.query
        .filter(AnalysisHistory.created_at >= cutoff)
        .with_entities(AnalysisHistory.created_at)
        .all()
    )

    # Group by "YYYY-MM" in Python
    counts: dict[str, int] = defaultdict(int)
    for (ts,) in records:
        if ts is None:
            continue
        # Handle both naive and timezone-aware datetimes
        if hasattr(ts, "tzinfo") and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        key = ts.strftime("%Y-%m")
        counts[key] += 1

    MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    result = []
    for ym in sorted(counts.keys()):
        try:
            m = int(ym.split("-")[1])
            result.append({"month": MONTH_ABBR[m - 1], "count": counts[ym]})
        except Exception:
            pass

    return jsonify(result)


# ── GET /admin/analyses ────────────────────────────────────────────────────────
@admin_bp.route("/analyses", methods=["GET"])
@jwt_required()
def analyses():
    _, err = _require_admin()
    if err:
        return err

    page     = request.args.get("page",     1,   type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search   = (request.args.get("search") or "").strip()

    query = AnalysisHistory.query
    if search:
        like = f"%{search}%"
        query = query.filter(
            AnalysisHistory.district.ilike(like)
            | AnalysisHistory.recommended_crop.ilike(like)
        )

    pagination = (
        query
        .order_by(AnalysisHistory.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Attach user email to each record
    items = []
    for a in pagination.items:
        d = a.to_dict(include_full=False)
        u = User.query.get(a.user_id)
        p = Profile.query.filter_by(user_id=a.user_id).first()
        d["user_email"] = u.email if u else "—"
        d["user_name"]  = (p.full_name if p and p.full_name else (u.email if u else "—"))
        items.append(d)

    return jsonify({
        "items":    items,
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
    })


# ── GET /admin/users ───────────────────────────────────────────────────────────
@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def users():
    _, err = _require_admin()
    if err:
        return err

    page     = request.args.get("page",     1,  type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search   = (request.args.get("search") or "").strip()

    query = User.query.filter_by(role="user")
    if search:
        like = f"%{search}%"
        query = query.filter(User.email.ilike(like))

    pagination = (
        query
        .order_by(User.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    items = []
    for u in pagination.items:
        p     = Profile.query.filter_by(user_id=u.id).first()
        count = AnalysisHistory.query.filter_by(user_id=u.id).count()
        last  = (
            AnalysisHistory.query.filter_by(user_id=u.id)
            .order_by(AnalysisHistory.created_at.desc())
            .first()
        )

        # "active today" heuristic
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        active_today = (
            AnalysisHistory.query
            .filter_by(user_id=u.id)
            .filter(AnalysisHistory.created_at >= today_start)
            .count() > 0
        )

        items.append({
            **u.to_dict(),
            "full_name":   p.full_name  if p else None,
            "district":    p.district   if p else None,
            "phone":       p.phone      if p else None,
            "analyses":    count,
            "last_analysis": last.created_at.isoformat() if last else None,
            "status":      "active" if active_today else "idle",
            "joined":      u.created_at.isoformat(),
        })

    return jsonify({
        "items":    items,
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
    })


# ── GET /admin/districts ───────────────────────────────────────────────────────
@admin_bp.route("/districts", methods=["GET"])
@jwt_required()
def districts():
    _, err = _require_admin()
    if err:
        return err

    rows = (
        db.session.query(
            AnalysisHistory.district,
            func.count().label("analyses"),
            func.avg(AnalysisHistory.ph).label("avg_ph"),
        )
        .group_by(AnalysisHistory.district)
        .order_by(func.count().desc())
        .all()
    )

    # Unique users per district
    user_rows = (
        db.session.query(
            AnalysisHistory.district,
            func.count(func.distinct(AnalysisHistory.user_id)).label("users"),
        )
        .group_by(AnalysisHistory.district)
        .all()
    )
    user_map = {r.district: r.users for r in user_rows}

    # Top crop per district
    crop_rows = (
        db.session.query(
            AnalysisHistory.district,
            AnalysisHistory.recommended_crop,
            func.count().label("cnt"),
        )
        .group_by(AnalysisHistory.district, AnalysisHistory.recommended_crop)
        .order_by(func.count().desc())
        .all()
    )
    top_crop_map: dict[str, str] = {}
    for r in crop_rows:
        if r.district not in top_crop_map:
            top_crop_map[r.district] = r.recommended_crop

    result = [
        {
            "district":  r.district,
            "analyses":  r.analyses,
            "users":     user_map.get(r.district, 0),
            "top_crop":  top_crop_map.get(r.district, "—"),
            "avg_ph":    round(r.avg_ph, 1) if r.avg_ph else None,
        }
        for r in rows
    ]

    return jsonify(result)


# ── GET /admin/crops ───────────────────────────────────────────────────────────
@admin_bp.route("/crops", methods=["GET"])
@jwt_required()
def crops():
    _, err = _require_admin()
    if err:
        return err

    rows = (
        db.session.query(
            AnalysisHistory.recommended_crop,
            func.count().label("count"),
        )
        .group_by(AnalysisHistory.recommended_crop)
        .order_by(func.count().desc())
        .limit(10)
        .all()
    )

    total = sum(r.count for r in rows) or 1
    result = [
        {
            "crop":  r.recommended_crop,
            "count": r.count,
            "pct":   round((r.count / total) * 100),
        }
        for r in rows
    ]
    return jsonify(result)


# ── GET /admin/fertilizers ─────────────────────────────────────────────────────
@admin_bp.route("/fertilizers", methods=["GET"])
@jwt_required()
def fertilizers():
    _, err = _require_admin()
    if err:
        return err

    rows = (
        db.session.query(
            AnalysisHistory.fertilizer_type,
            func.count().label("count"),
        )
        .filter(AnalysisHistory.fertilizer_type.isnot(None))
        .group_by(AnalysisHistory.fertilizer_type)
        .order_by(func.count().desc())
        .limit(8)
        .all()
    )

    total = sum(r.count for r in rows) or 1
    result = [
        {
            "name":  r.fertilizer_type,
            "count": r.count,
            "pct":   round((r.count / total) * 100),
        }
        for r in rows
    ]
    return jsonify(result)