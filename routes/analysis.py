import logging
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import db, AnalysisHistory

logger = logging.getLogger("soilsense.analysis")
analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")


def _bad(msg: str, code: int = 400):
    return jsonify({"error": msg}), code


@analysis_bp.route("/", methods=["POST"])
@jwt_required()
def add_analysis():
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}

    if not data.get("district") or not data.get("recommended_crop"):
        return _bad("Missing required fields: district, recommended_crop")

    crops      = data.get("all_crops", [])
    top_crop   = crops[0] if crops else {}
    fert_plan  = top_crop.get("fertilizerPlan", {})
    yield_pred = top_crop.get("yieldPrediction", {})
    pest_risk  = top_crop.get("pestDiseaseRisk", {})

    record = AnalysisHistory(
        user_id = user_id,

     
        district     = data.get("district"),
        climate_zone = data.get("climate_zone"),
        input_mode   = data.get("input_mode", "lab"),

        land_use      = data.get("land_use"),
        previous_crop = data.get("previous_crop") or None,

        nitrogen       = data.get("nitrogen"),
        phosphorus     = data.get("phosphorus"),
        potassium      = data.get("potassium"),
        ph             = data.get("ph"),
        moisture       = data.get("moisture"),
        temperature    = data.get("temperature"),
        organic_matter = data.get("organicMatter") or data.get("organic_matter"),

       
        rainfall_mm       = data.get("rainfall_mm"),
        rainfall_band     = data.get("rainfall_band"),
        rainfall_category = data.get("rainfall_category"),

        recommended_crop = data.get("recommended_crop"),
        crop_score       = data.get("crop_score"),
        crop_confidence  = data.get("crop_confidence"),
        crop_season      = data.get("crop_season"),
        fertilizer_type  = fert_plan.get("basal") or data.get("fertilizer_type"),
        yield_predicted  = yield_pred.get("predicted_tha") or data.get("yield_predicted"),
        yield_potential  = yield_pred.get("potential_tha") or data.get("yield_potential"),
        yield_category   = yield_pred.get("yield_category") or data.get("yield_category"),
        pest_risk_level  = pest_risk.get("summary", {}).get("level") or data.get("pest_risk_level"),

      
        all_crops_json   = crops,
        soil_alerts_json = data.get("soil_alerts", []),
    )

    db.session.add(record)
    db.session.commit()

    logger.info("Analysis saved — user=%s crop=%s district=%s",
                user_id, record.recommended_crop, record.district)
    return jsonify({"message": "Analysis saved.", "id": record.id}), 201


@analysis_bp.route("/", methods=["GET"])
@jwt_required()
def get_analyses():
    user_id  = get_jwt_identity()
    page     = request.args.get("page",     1,  type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    district = request.args.get("district")

    query = AnalysisHistory.query.filter_by(user_id=user_id)
    if district:
        query = query.filter(AnalysisHistory.district.ilike(f"%{district}%"))

    pagination = query.order_by(AnalysisHistory.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "items":    [a.to_dict(include_full=True) for a in pagination.items],
        "total":    pagination.total,
        "page":     pagination.page,
        "pages":    pagination.pages,
        "per_page": pagination.per_page,
    })


@analysis_bp.route("/<string:analysis_id>", methods=["GET"])
@jwt_required()
def get_analysis(analysis_id: str):
    user_id = get_jwt_identity()
    record  = AnalysisHistory.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not record:
        return _bad("Analysis not found.", 404)
    return jsonify(record.to_dict(include_full=True))


@analysis_bp.route("/<string:analysis_id>", methods=["DELETE"])
@jwt_required()
def delete_analysis(analysis_id: str):
    user_id = get_jwt_identity()
    record  = AnalysisHistory.query.filter_by(id=analysis_id, user_id=user_id).first()
    if not record:
        return _bad("Analysis not found.", 404)
    db.session.delete(record)
    db.session.commit()
    return jsonify({"message": "Analysis deleted."})


@analysis_bp.route("/stats", methods=["GET"])
@jwt_required()
def get_stats():
    from sqlalchemy import func
    user_id = get_jwt_identity()

    total = AnalysisHistory.query.filter_by(user_id=user_id).count()

  
    top_crop_row = (
        db.session.query(
            AnalysisHistory.recommended_crop,
            func.count(AnalysisHistory.recommended_crop).label("cnt"),
        )
        .filter_by(user_id=user_id)
        .group_by(AnalysisHistory.recommended_crop)
        .order_by(func.count(AnalysisHistory.recommended_crop).desc())
        .first()
    )

    top_district_row = (
        db.session.query(
            AnalysisHistory.district,
            func.count(AnalysisHistory.district).label("cnt"),
        )
        .filter_by(user_id=user_id)
        .group_by(AnalysisHistory.district)
        .order_by(func.count(AnalysisHistory.district).desc())
        .first()
    )

    last = (
        AnalysisHistory.query.filter_by(user_id=user_id)
        .order_by(AnalysisHistory.created_at.desc())
        .first()
    )

    return jsonify({
        "total_analyses":         total,
  
        "most_common_crop":       top_crop_row.recommended_crop if top_crop_row     else None,
        "most_analysed_district": top_district_row.district     if top_district_row else None,
      
        "last_analysis":          last.to_dict(include_full=False) if last          else None,
    })