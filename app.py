import os
import logging
from datetime import timedelta

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from dotenv import load_dotenv

load_dotenv()

from config import Config
from models import db

from routes.recommend import recommend_bp
from routes.rainfall  import rainfall_bp
from routes.chat      import chat_bp
from routes.admin     import admin_bp
from routes.admin_chatbot     import admin_chatbot_bp
from routes.admin_extended import admin_ext_bp
from routes.auth      import auth_bp
from routes.profiles  import profiles_bp
from routes.analysis  import analysis_bp


logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("soilsense")

BASE = os.path.dirname(os.path.abspath(__file__))

_REQUIRED_MODELS = [
    "best_crop_model.pkl",
    "crop_scaler.pkl",
    "crop_label_encoder.pkl",
    "best_fert_model.pkl",
    "fert_scaler.pkl",
    "fert_label_encoder.pkl",
    "soil_type_encoder.pkl",
    "crop_type_encoder.pkl",
]


def _check_models() -> dict:
    status = {}
    for fname in _REQUIRED_MODELS:
        path = os.path.join(BASE, "models", fname)
        status[fname] = "ok" if os.path.exists(path) else "MISSING"
        if status[fname] == "MISSING":
            logger.warning("Model file not found: %s — run train_models.py", fname)
    return status


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        minutes=config_object.JWT_ACCESS_TOKEN_EXPIRES_MINUTES
    )

    CORS(app, supports_credentials=True)
    
    app.register_blueprint(admin_chatbot_bp)
    
    db.init_app(app)
    Migrate(app, db)
    jwt = JWTManager(app)

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": "Authorization token missing.", "detail": reason}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": "Invalid token.", "detail": reason}), 422

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return jsonify({"error": "Token has expired. Please log in again."}), 401

    # ── Blueprints ─────────────────────────────────────────────────────────────
    app.register_blueprint(recommend_bp, url_prefix="/api")
    app.register_blueprint(rainfall_bp,  url_prefix="/api")
    app.register_blueprint(chat_bp,      url_prefix="/api")

    app.register_blueprint(auth_bp)       # /auth/*
    app.register_blueprint(profiles_bp)   # /profiles/*
    app.register_blueprint(analysis_bp)   # /analysis/*
    app.register_blueprint(admin_bp)      # /admin/*
    app.register_blueprint(admin_ext_bp)   # /admin/* (extended)  ← must be inside create_app

    @app.route("/")
    def home():
        return jsonify({
            "message": "NthakaGuide API is running!",
            "version": "3.0",
            "endpoints": {
                "recommend":       "POST /api/recommend",
                "rainfall":        "POST /api/rainfall",
                "chat":            "POST /api/chat",
                "health":          "GET  /api/health",
                "register":        "POST /auth/register",
                "login":           "POST /auth/login",
                "me":              "GET  /auth/me",
                "admin_slots":     "GET  /auth/admin-slots",
                "change_password": "PUT  /auth/change-password",
                "profile_get":     "GET  /profiles/",
                "profile_update":  "PUT  /profiles/",
                "analysis_save":   "POST /analysis/",
                "analysis_list":   "GET  /analysis/",
                "analysis_get":    "GET  /analysis/<id>",
                "analysis_stats":  "GET  /analysis/stats",
                "analysis_delete": "DELETE /analysis/<id>",
                "admin_stats":     "GET  /admin/stats",
                "admin_monthly":   "GET  /admin/monthly",
                "admin_analyses":  "GET  /admin/analyses",
                "admin_users":     "GET  /admin/users",
                "admin_districts": "GET  /admin/districts",
                "admin_crops":     "GET  /admin/crops",
                "admin_ferts":     "GET  /admin/fertilizers",
            },
        })

    @app.route("/api/health")
    def health():
        model_status = _check_models()
        all_ok       = all(v == "ok" for v in model_status.values())

        db_ok = True
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception as exc:
            db_ok = False
            logger.error("DB health check failed: %s", exc)

        status_code = 200 if (all_ok and db_ok) else 503

        return jsonify({
            "status":   "ok" if (all_ok and db_ok) else "degraded",
            "service":  "NthakaGuide API",
            "version":  "3.0",
            "database": "ok" if db_ok else "unreachable",
            "models":   model_status,
            "rainfall_sources": [
                "Open-Meteo Live Forecast",
                "NASA POWER Satellite",
                "EWMA Historical Forecast",
                "District Historical Average",
            ],
            "features": {
                "ml_crop_prediction":      True,
                "district_climate_zones":  True,
                "live_rainfall_forecast":  True,
                "satellite_rainfall":      True,
                "crop_fertilizer_plans":   True,
                "yield_prediction":        True,
                "pest_disease_risk":       True,
                "land_use_filtering":      True,
                "crop_rotation_advice":    True,
                "user_authentication":     True,
                "analysis_history":        True,
                "profile_management":      True,
                "admin_dashboard":         True,
            },
        }), status_code

    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory("static", "favicon.ico")

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Bad request.", "detail": str(e)}), 400

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found."}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed."}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Internal server error")
        return jsonify({"error": "Internal server error."}), 500

    return app


app = create_app()


if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "development") == "development"

    logger.info("Checking ML model files …")
    status  = _check_models()
    missing = [k for k, v in status.items() if v == "MISSING"]
    if missing:
        logger.warning(
            "%d model file(s) missing. Run `python train_models.py` first.\n  Missing: %s",
            len(missing), ", ".join(missing),
        )
    else:
        logger.info("All ML model files found ✅")

    with app.app_context():
        db.create_all()
        logger.info("Database tables verified ✅")

    logger.info("NthakaGuide API starting on http://localhost:%d", port)
    app.run(host="0.0.0.0", port=port, debug=debug)