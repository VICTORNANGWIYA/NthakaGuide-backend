

import os
import joblib          # ← replaces pickle
import numpy as np
from flask import Blueprint, request, jsonify

from data.crop_data            import CROP_STATISTICS, MALAWI_CROP_MAP
from data.rainfall_data        import MALAWI_DISTRICTS
from data.climate_zones        import CLIMATE_ZONES, ZONE_CROPS, ZONE_DESCRIPTIONS, DEFAULT_ZONE
from data.district_coordinates import DISTRICT_COORDINATES
from data.land_use_map         import LAND_USE_MAP, LAND_USE_LABELS

from utils.algorithms import (
    get_rainfall_band,
    get_band_description,
    get_soil_alerts,
    assess_soil,
    adjust_for_rainfall,
    generate_fertilizer_plan,
)
from utils.weather_api        import get_live_rainfall
from utils.satellite_rainfall import get_satellite_annual_history
from utils.rotation_advice    import get_rotation_advice, get_general_rotation_tip

recommend_bp = Blueprint("recommend", __name__)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


crop_model   = joblib.load(os.path.join(BASE, "models/best_crop_model.pkl"))
crop_scaler  = joblib.load(os.path.join(BASE, "models/crop_scaler.pkl"))
crop_encoder = joblib.load(os.path.join(BASE, "models/crop_label_encoder.pkl"))




_BUILT_IN_CROP_MAP = {
    "banana":      "Banana",      "blackgram":   "Black Gram",
    "chickpea":    "Chickpea",    "coconut":     "Coconut",
    "coffee":      "Coffee",      "cotton":      "Cotton",
    "kidneybeans": "Kidney Beans","lentil":      "Lentil",
    "maize":       "Maize",       "mungbean":    "Mung Bean",
    "pigeonpeas":  "Pigeon Peas", "rice":        "Rice",
    "beans":       "Beans",       "cassava":     "Cassava",
    "groundnuts":  "Groundnuts",  "soybean":     "Soybean",
    "millet":      "Millet",      "sweetpotato": "Sweet Potato",
    "sorghum":     "Sorghum",     "tobacco":     "Tobacco",
    "cowpea":      "Cowpea",      "sunflower":   "Sunflower",
    "sesame":      "Sesame",      "tomato":      "Tomato",
    "onion":       "Onion",       "cabbage":     "Cabbage",
    "papaya":      "Papaya",      "mango":       "Mango",
    "sugarcane":   "Sugarcane",   "okra":        "Okra",
    "pumpkin":     "Pumpkin",     "watermelon":  "Watermelon",
    "guava":       "Guava",       "orange":      "Orange",
    "chili":       "Chilli",      "cucumber":    "Cucumber",
    "eggplant":    "Eggplant",    "muskmelon":   "Muskmelon",
    "potato":      "Potato",      "tea":         "Tea",
}

def _resolve_display_name(crop_raw: str) -> str:
    return (
        MALAWI_CROP_MAP.get(crop_raw)
        or _BUILT_IN_CROP_MAP.get(crop_raw)
        or crop_raw.replace("_", " ").title()
    )




def _infer_soil_type(ph: float, organic_matter: float, moisture: float) -> str:
    """
    Simple heuristic to infer a soil-type label from available inputs.
    Ideally the frontend would pass soil_type directly — add it as an
    optional field if you extend the form later.
    """
    if ph < 5.5 and organic_matter > 3.0:
        return "peaty"
    if ph > 7.5:
        return "alkaline"
    if ph < 5.5:
        return "acidic"
    if moisture > 60:
        return "clay"
    if moisture < 25:
        return "sandy"
    return "loamy"


def _build_fertilizer_plan(
    crop_raw:      str,
    crop_display:  str,
    nitrogen:      float,
    phosphorus:    float,
    potassium:     float,
    ph:            float,
    organic:       float,
    moisture:      float,
    annual_mm:     float,
    rainfall_band: str,
    rainfall_cat:  str,
) -> dict:
    """
    Generate a rich fertilizer plan by combining:
      1. adjust_for_rainfall  — rainfall/crop/pH/soil-aware NPK timing plan
      2. generate_fertilizer_plan — deficiency-corrective items from soil test

    Returns a dict matching the frontend FertilizerPlan interface:
      {
        items:         [ { type, applicationRate, timing, notes, alternative, confidence, products } ]
        warnings:      [ str ]
        organicAdvice: str
        confidence:    { score, label, message }
        # legacy flat fields kept for backward compat
        basal:           str | None
        basal_rate:      str | None
        topdress:        str | None
        topdress_rate:   str | None
        topdress_timing: str | None
        notes:           str | None
      }
    """
    soil_type = _infer_soil_type(ph, organic, moisture)

    
    rain_plan = adjust_for_rainfall(
        annual_mm  = annual_mm,
        crop       = crop_raw,
        ph         = ph,
        soil_type  = soil_type,
    )

    
    deficiency_items = generate_fertilizer_plan(
        N             = nitrogen,
        P             = phosphorus,
        K             = potassium,
        ph            = ph,
        organic_matter= organic,
        rainfall_cat  = rainfall_cat,
        soil_type     = soil_type,
        crop          = crop_raw,
    )

    
    rain_items = []
    for step in rain_plan.get("plan", []):
        products   = step.get("products", [])
        rate_str   = ", ".join(products) if products else "—"
        rain_items.append({
            "type":            step.get("action", "Apply fertilizer"),
            "applicationRate": rate_str,
            "timing":          step.get("timing", ""),
            "notes":           step.get("note", ""),
            "alternative":     None,
            "confidence":      None,
            "products":        products,
        })

    
    def_items = []
    for d in deficiency_items:
        def_items.append({
            "type":            d.get("type", ""),
            "applicationRate": d.get("applicationRate", ""),
            "timing":          d.get("timing", ""),
            "notes":           d.get("notes", ""),
            "alternative":     d.get("alternative"),
            "confidence":      d.get("confidence"),
            "products":        [d.get("type", "")],
        })

    
    
    merged_items = rain_items[:]

    rain_product_types = {
        item["type"].lower()[:30] for item in rain_items
    }

    for d_item in def_items:
        
       
        is_correction = any(
            kw in d_item["type"].lower()
            for kw in ("lime", "sulphur", "compost", "manure", "maintenance")
        )
        already_covered = d_item["type"].lower()[:30] in rain_product_types

        if is_correction or not already_covered:
            merged_items.append(d_item)

   
    all_warnings = list(rain_plan.get("warnings", []))

    
    basal           = None
    basal_rate      = None
    topdress        = None
    topdress_rate   = None
    topdress_timing = None
    notes_legacy    = rain_plan.get("cropNote") or None

    for step in rain_plan.get("plan", []):
        products = step.get("products", [])
        timing   = step.get("timing", "").lower()

        if "planting" in timing and basal is None:
            basal      = step.get("action", "")
            basal_rate = ", ".join(products) if products else None

        elif "top-dressing 1" in timing or "top-dress" in step.get("timing", "").lower():
            if topdress is None:
                topdress        = step.get("action", "")
                topdress_rate   = ", ".join(products) if products else None
                topdress_timing = step.get("timing", "")

    return {
        # Rich new fields
        "items":         merged_items,
        "warnings":      all_warnings,
        "organicAdvice": rain_plan.get("organicAdvice", ""),
        "confidence":    rain_plan.get("confidence"),

        # Legacy flat fields (for backward compat / PDF report)
        "basal":           basal,
        "basal_rate":      basal_rate,
        "topdress":        topdress,
        "topdress_rate":   topdress_rate,
        "topdress_timing": topdress_timing,
        "notes":           notes_legacy,
    }




def predict_crop_ml(N, P, K, temperature, humidity, ph, annual_rainfall_mm):
    """
    Run the trained ML model and return ALL crops ranked by probability.
    Never pass the 7-day live forecast — always use annual_mm here.
    """
    features        = np.array([[N, P, K, temperature, humidity, ph, annual_rainfall_mm]])
    features_scaled = crop_scaler.transform(features)
    raw_probs       = crop_model.predict_proba(features_scaled)[0]

    pairs = sorted(
        zip(crop_encoder.classes_, raw_probs),
        key=lambda x: x[1],
        reverse=True,
    )

    return [
        {
            "crop":     _resolve_display_name(crop_raw),
            "crop_raw": crop_raw,
            "raw_prob": prob,
        }
        for crop_raw, prob in pairs
    ]


def rescale_confidences(predictions: list) -> list:
    """Rescale raw probs so they sum to 100% within the filtered list."""
    if not predictions:
        return predictions

    total = sum(p["raw_prob"] for p in predictions)

    if total == 0:
        n = len(predictions)
        for p in predictions:
            p["confidence"] = round(100.0 / n, 1)
        return predictions

    for p in predictions:
        p["confidence"] = round((p["raw_prob"] / total) * 100, 1)

    return predictions



TARGET = 5

def _apply_filters(all_predictions: list, allowed_zone: set, allowed_use: set) -> list:
    """
    Progressively relax filters until we have TARGET crops.
    Always returns up to TARGET predictions.
    """
    selected  = []
    seen_raws = set()

    def _fill(candidates: list, pool: set) -> None:
        for p in candidates:
            if len(selected) >= TARGET:
                return
            raw = p["crop_raw"].lower()
            if raw in pool and raw not in seen_raws:
                selected.append(p)
                seen_raws.add(raw)

    # Pass 1 — zone ∩ land-use
    _fill(all_predictions, allowed_zone & allowed_use)

    # Pass 2 — land-use only
    if len(selected) < TARGET:
        _fill(all_predictions, allowed_use - allowed_zone)

    # Pass 3 — zone only
    if len(selected) < TARGET:
        _fill(all_predictions, allowed_zone - allowed_use)

    # Pass 4 — any remaining (by ML confidence)
    if len(selected) < TARGET:
        for p in all_predictions:
            if len(selected) >= TARGET:
                break
            raw = p["crop_raw"].lower()
            if raw not in seen_raws:
                selected.append(p)
                seen_raws.add(raw)

    return selected




def resolve_rainfall(district_name: str, district: dict) -> dict:
    """
    1. NASA POWER satellite — annual history 2000→present, EWMA (85% conf)
    2. District historical average — fallback only (55% conf)

    live_7day_mm is from Open-Meteo — display only, NEVER fed to ML model.
    """
    coords = DISTRICT_COORDINATES.get(district_name)

    live_7day_mm = None
    live_daily   = None
    if coords:
        live = get_live_rainfall(coords[0], coords[1])
        if live:
            live_7day_mm = live["total_mm"]
            live_daily   = live["daily_forecast"]

    annual_mm         = None
    annual_source     = None
    annual_confidence = 60
    historical_years  = []
    historical_values = []

    if coords:
        hist = get_satellite_annual_history(coords[0], coords[1])
        if hist and hist.get("annual_mm"):
            annual_mm         = hist["annual_mm"]
            annual_source     = hist["source"]
            annual_confidence = 85
            historical_years  = hist["years"]
            historical_values = hist["values"]

    if annual_mm is None:
        annual_mm         = district["avgRainfallMm"]
        annual_source     = "District Historical Average"
        annual_confidence = 55

    return {
        "annual_mm":         annual_mm,
        "annual_source":     annual_source,
        "annual_confidence": annual_confidence,
        "historical_years":  historical_years,
        "historical_values": historical_values,
        "live_7day_mm":      live_7day_mm,
        "live_daily":        live_daily,
    }




def build_reason(
    rank, crop_name, confidence,
    district_name, annual_mm, rainfall_band,
    land_use="food", previous_crop="",
):
    rank_labels = [
        "Best choice", "Second choice", "Third choice",
        "Fourth choice", "Fifth choice",
    ]
    rank_label = rank_labels[rank] if rank < len(rank_labels) else f"Choice #{rank + 1}"

    band_plain = {
        "Very Low": "very dry conditions",
        "Low":      "dry conditions",
        "Moderate": "average rainfall",
        "High":     "good rainfall",
        "Very High":"very high rainfall",
    }.get(rainfall_band, rainfall_band)

    conf_plain = (
        "very well suited"  if confidence >= 60 else
        "well suited"       if confidence >= 35 else
        "moderately suited" if confidence >= 15 else
        "worth considering"
    )

    use_label = LAND_USE_LABELS.get(land_use, land_use)

    reason = (
        f"{rank_label} for {district_name}. "
        f"This crop is {conf_plain} to your soil and "
        f"the {band_plain} ({annual_mm:,}mm/yr). "
        f"Suits your {use_label} goal."
    )

    if previous_crop and previous_crop.lower() not in ("", "none", "unknown"):
        reason += f" Evaluated in rotation after {previous_crop.title()}."

    return reason




@recommend_bp.route("/recommend", methods=["POST"])
def recommend():

    body = request.get_json(silent=True) or {}

    required = [
        "nitrogen", "phosphorus", "potassium", "ph",
        "moisture", "temperature", "organicMatter", "districtName",
    ]
    missing = [f for f in required if body.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    nitrogen      = float(body["nitrogen"])
    phosphorus    = float(body["phosphorus"])
    potassium     = float(body["potassium"])
    ph            = float(body["ph"])
    moisture      = float(body["moisture"])
    temperature   = float(body["temperature"])
    organic       = float(body["organicMatter"])
    district_name = body["districtName"]

    land_use      = (body.get("landUse")      or "food").lower().strip()
    previous_crop = (body.get("previousCrop") or "").lower().strip()

    if land_use not in LAND_USE_MAP:
        land_use = "food"

    district = next(
        (d for d in MALAWI_DISTRICTS if d["name"] == district_name), None
    )
    if not district:
        return jsonify({"error": f"Unknown district: {district_name}"}), 400

    
    rainfall_data     = resolve_rainfall(district_name, district)
    annual_mm         = rainfall_data["annual_mm"]
    annual_source     = rainfall_data["annual_source"]
    annual_confidence = rainfall_data["annual_confidence"]
    historical_years  = rainfall_data["historical_years"]
    historical_values = rainfall_data["historical_values"]
    live_7day_mm      = rainfall_data["live_7day_mm"]
    live_daily        = rainfall_data["live_daily"]

    rainfall_band = get_rainfall_band(annual_mm)

    rainfall_category = (
        "Very Low"  if annual_mm < 400  else
        "Low"       if annual_mm < 650  else
        "Moderate"  if annual_mm < 950  else
        "High"      if annual_mm < 1400 else
        "Very High"
    )

    
    all_predictions = predict_crop_ml(
        nitrogen, phosphorus, potassium,
        temperature, moisture, ph,
        annual_mm,
    )

    zone         = CLIMATE_ZONES.get(district_name, DEFAULT_ZONE)
    allowed_zone = {c.lower() for c in ZONE_CROPS.get(zone, [])}
    allowed_use  = {c.lower() for c in LAND_USE_MAP.get(land_use, [])}

    filtered = _apply_filters(all_predictions, allowed_zone, allowed_use)
    filtered = rescale_confidences(filtered)

    
    crops = []
    for i, pred in enumerate(filtered):

        crop_display = pred["crop"]
        crop_raw     = pred["crop_raw"]

        stat = next(
            (c for c in CROP_STATISTICS
             if _resolve_display_name(c["label"]) == crop_display
             or c["label"] == crop_raw),
            None,
        )

        
        fertilizer_plan = _build_fertilizer_plan(
            crop_raw      = crop_raw,
            crop_display  = crop_display,
            nitrogen      = nitrogen,
            phosphorus    = phosphorus,
            potassium     = potassium,
            ph            = ph,
            organic       = organic,
            moisture      = moisture,
            annual_mm     = annual_mm,
            rainfall_band = rainfall_band,
            rainfall_cat  = rainfall_category,
        )

        rotation_advice = get_rotation_advice(previous_crop, crop_raw)

        crops.append({
            "crop":       crop_display,
            "confidence": pred["confidence"],
            "score":      max(10, round(95 - i * 10)),
            "season":     stat["season"] if stat else "Oct–Apr",
            "emoji":      stat["emoji"]  if stat else "🌱",

            "reason": build_reason(
                i, crop_display, pred["confidence"],
                district_name, annual_mm, rainfall_band,
                land_use, previous_crop,
            ),

            "fertilizerPlan": fertilizer_plan,
            "rotationAdvice": rotation_advice,
        })

    
    soil_alerts     = get_soil_alerts(nitrogen, phosphorus, potassium, ph, annual_mm)
    soil_assessment = assess_soil(nitrogen, phosphorus, potassium, ph, organic, moisture)
    rotation_tip    = get_general_rotation_tip(previous_crop)

    return jsonify({
        "crops": crops,

        "farmerContext": {
            "landUse":      land_use,
            "landUseLabel": LAND_USE_LABELS.get(land_use, land_use),
            "previousCrop": previous_crop or None,
            "rotationTip":  rotation_tip,
        },

        "rainfall": {
            "annualForecastMm":    annual_mm,
            "annualSource":        annual_source,
            "annualConfidence":    annual_confidence,
            "annualBand":          rainfall_band,
            "annualCategory":      rainfall_category,
            "annualDescription":   get_band_description(annual_mm),
            "historicalYears":     historical_years,
            "historicalValues":    historical_values,
            "live7DayMm":          live_7day_mm,
            "live7DayDescription": (
                f"Expected rainfall in the next 7 days: {live_7day_mm}mm"
                if live_7day_mm is not None else None
            ),
            "liveDailyForecast":   live_daily,
        },

        
        "forecastedRainfall":      annual_mm,
        "rainfallSource":          annual_source,
        "rainfallBand":            rainfall_band,
        "rainfallCategory":        rainfall_category,
        "rainfallBandDescription": get_band_description(annual_mm),

        "soilAssessment": soil_assessment,
        "soilAlerts":     soil_alerts,

        "districtInfo": {
            "district":        district_name,
            "climateZone":     zone,
            "zoneDescription": ZONE_DESCRIPTIONS.get(zone, ""),
        },

        "mlPrediction": {
            "algorithm": "Random Forest (smooth probabilities)",
            "topCrop":   filtered[0]["crop"]       if filtered else None,
            "topConf":   filtered[0]["confidence"] if filtered else None,
        },
    })