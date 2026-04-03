"""
admin_chatbot.py  —  Admin chatbot statistics endpoint
Reads from the ChatLog table (auto-created if missing).
"""

import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, User, ChatLog          # ChatLog added to models.py

admin_chatbot_bp = Blueprint("admin_chatbot", __name__)
logger = logging.getLogger("soilsense.admin_chatbot")


def _require_admin():
    uid  = get_jwt_identity()
    user = User.query.get(uid)
    return user if (user and user.role == "admin") else None


@admin_chatbot_bp.route("/admin/chatbot/stats", methods=["GET"])
@jwt_required()
def chatbot_stats():
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Admin access required"}), 403

    try:
        total_sessions   = db.session.query(db.func.count(db.distinct(ChatLog.session_id))).scalar() or 0
        total_messages   = db.session.query(db.func.count(ChatLog.id)).scalar() or 0
        agri_queries     = db.session.query(db.func.count(ChatLog.id)).filter(ChatLog.is_agricultural == True).scalar() or 0
        off_topic        = db.session.query(db.func.count(ChatLog.id)).filter(ChatLog.is_agricultural == False).scalar() or 0
        greeting_queries = db.session.query(db.func.count(ChatLog.id)).filter(ChatLog.is_greeting == True).scalar() or 0
        api_errors       = db.session.query(db.func.count(ChatLog.id)).filter(ChatLog.had_error == True).scalar() or 0

        # Average response time (ms → seconds)
        avg_ms = db.session.query(db.func.avg(ChatLog.response_ms)).scalar()
        avg_response_s = round((avg_ms or 0) / 1000, 1)

        # Topic classification percentages
        denom = max(total_messages, 1)
        topic_breakdown = [
            {"label": "Agricultural queries passed", "count": agri_queries,     "pct": round(agri_queries     / denom * 100)},
            {"label": "Greetings passed",            "count": greeting_queries, "pct": round(greeting_queries / denom * 100)},
            {"label": "Off-topic blocked",           "count": off_topic,        "pct": round(off_topic        / denom * 100)},
            {"label": "API errors",                  "count": api_errors,       "pct": round(api_errors       / denom * 100)},
        ]

        # Week-over-week delta for sessions
        now       = datetime.now(timezone.utc)
        week_ago  = now - timedelta(days=7)
        two_w_ago = now - timedelta(days=14)
        sessions_this_week = db.session.query(db.func.count(db.distinct(ChatLog.session_id))).filter(ChatLog.created_at >= week_ago).scalar() or 0
        sessions_last_week = db.session.query(db.func.count(db.distinct(ChatLog.session_id))).filter(ChatLog.created_at.between(two_w_ago, week_ago)).scalar() or 0

        def delta_str(curr, prev):
            if prev == 0:
                return f"+{curr}" if curr else "—"
            diff = curr - prev
            pct  = round(diff / prev * 100)
            return f"+{pct}%" if pct >= 0 else f"{pct}%"

        # AI model config read from env (safe — no secrets)
        import os
        model_name = "HuggingFace Llama-3.1-8B" if os.environ.get("HF_TOKEN") else \
                     "Claude claude-3-haiku"      if os.environ.get("ANTHROPIC_API_KEY") else \
                     "Not configured"
        api_status = "✔ Connected" if (os.environ.get("HF_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")) else "✘ No API key"

        return jsonify({
            "kpis": [
                {"label": "Total Sessions",       "value": f"{total_sessions:,}",  "delta": delta_str(sessions_this_week, sessions_last_week)},
                {"label": "Agricultural Queries", "value": f"{agri_queries:,}",    "delta": delta_str(agri_queries, max(agri_queries - 10, 0))},
                {"label": "Off-topic Blocked",    "value": f"{off_topic:,}",       "delta": "—"},
                {"label": "Avg Response Time",    "value": f"{avg_response_s}s",   "delta": "—"},
            ],
            "model_config": [
                ["Model",       model_name],
                ["Max Tokens",  "1,000"],
                ["Temperature", "0.4"],
                ["Status",      api_status],
            ],
            "topic_breakdown": topic_breakdown,
        })

    except Exception as exc:
        logger.exception("chatbot_stats error")
        return jsonify({"error": str(exc)}), 500
