
from flask import Blueprint, request, jsonify

from data.rainfall_data        import DISTRICT_DEFAULTS
from data.district_coordinates import DISTRICT_COORDINATES

from utils.algorithms import (
    get_rainfall_band,
    get_band_description,
    get_monthly_distribution,
    get_crop_suitability_by_rainfall,
    get_fertilizer_calendar,
)
from utils.weather_api        import get_live_rainfall
from utils.satellite_rainfall import (
    get_satellite_annual_history,
    get_satellite_monthly,
    get_satellite_daily,
)
from utils.season_helper import (
    get_season_label,
    get_weekly_summary,
    estimate_season_total,
)

rainfall_bp = Blueprint("rainfall", __name__)


@rainfall_bp.route("/rainfall", methods=["POST"])
def rainfall():

    body          = request.get_json(silent=True) or {}
    district_name = body.get("districtName")

    if not district_name:
        return jsonify({"error": "Missing districtName"}), 400

    if district_name not in DISTRICT_DEFAULTS and district_name not in DISTRICT_COORDINATES:
        return jsonify({"error": f"Unknown district: {district_name}"}), 400

    avg_annual = DISTRICT_DEFAULTS.get(district_name, 900)
    coords     = DISTRICT_COORDINATES.get(district_name)

    season = get_season_label()

    live_7day_mm = None
    live_daily   = None
    if coords:
        live = get_live_rainfall(coords[0], coords[1])
        if live:
            live_7day_mm = live["total_mm"]
            live_daily   = live["daily_forecast"]

    historical_years  = []
    historical_values = []
    annual_mm         = None
    annual_confidence = 60
    annual_source     = "District Historical Average"

    if coords:
        hist = get_satellite_annual_history(coords[0], coords[1])
        if hist:
            historical_years  = hist["years"]
            historical_values = hist["values"]
            annual_mm         = hist["annual_mm"]
            annual_confidence = 85
            annual_source     = f"NASA POWER Satellite (2000–{historical_years[-1]})" \
                                if historical_years else "NASA POWER Satellite"

    if annual_mm is None:
        annual_mm         = avg_annual
        annual_confidence = 55
        annual_source     = "District Historical Average"

    monthly_data = None
    if coords:
        m = get_satellite_monthly(coords[0], coords[1])
        if m:
            monthly_data = m["monthly"]

 
    if monthly_data:
        monthly_distribution = [
            {"month": item["month"], "mm": item["mm"]}
            for item in monthly_data
        ]
    else:
        monthly_distribution = get_monthly_distribution(annual_mm)

    daily_data  = None
    weekly_data = []
    if coords:
        d = get_satellite_daily(coords[0], coords[1], days=30)
        if d:
            daily_data  = d["daily"]
            weekly_data = get_weekly_summary(daily_data)

    season_totals = estimate_season_total(monthly_distribution, annual_mm)

    band = get_rainfall_band(annual_mm)

    risks          = []
    below_avg_warn = False

    if band == "Very High":
        risks.append({
            "level":   "danger",
            "icon":    "🌊",
            "message": (
                f"Very heavy rainfall expected ({annual_mm:,}mm/yr). "
                "Build drainage ridges to prevent waterlogging and crop loss."
            ),
        })
    elif band == "High":
        risks.append({
            "level":   "warning",
            "icon":    "🌊",
            "message": (
                f"High rainfall expected ({annual_mm:,}mm/yr). "
                "Split nitrogen fertilizer into 2–3 applications to reduce leaching."
            ),
        })
    elif band == "Very Low":
        risks.append({
            "level":   "danger",
            "icon":    "🌵",
            "message": (
                f"Very low rainfall expected ({annual_mm:,}mm/yr). "
                "Only grow drought-tolerant crops: sorghum, millet, cowpea. "
                "Consider supplementary irrigation."
            ),
        })
        below_avg_warn = True  
    elif band == "Low":
        risks.append({
            "level":   "warning",
            "icon":    "🌵",
            "message": (
                f"Low rainfall expected ({annual_mm:,}mm/yr). "
                "Use drought-tolerant varieties and apply mulch to conserve moisture."
            ),
        })
        below_avg_warn = True

    
    if not below_avg_warn and annual_mm < avg_annual * 0.85:
        risks.append({
            "level":   "warning",
            "icon":    "📉",
            "message": (
                f"Below-average rainfall forecast ({annual_mm:,}mm vs usual "
                f"{avg_annual:,}mm). Plan for possible mid-season dry spells."
            ),
        })

    if not risks:
        risks.append({
            "level":   "ok",
            "icon":    "✅",
            "message": "Rainfall outlook is normal. Good conditions for most crops.",
        })

    return jsonify({
   
        "annualForecastMm":    annual_mm,
        "annualSource":        annual_source,
        "annualConfidence":    annual_confidence,
        "band":                band,
        "bandDescription":     get_band_description(annual_mm),
        "avgAnnualRainfall":   avg_annual,

       
        "seasonLabel":         season["label"],
        "seasonPeriod":        season["period"],
        "inRainySeason":       season["in_rainy_season"],
        "seasonTotalMm":       season_totals["season_total_mm"],
        "seasonMonths":        season_totals["season_months"],

        "historicalYears":     historical_years,
        "historicalValues":    historical_values,
        "stationName":         annual_source,

        "monthlyDistribution": monthly_distribution,

      
        "dailyData":           daily_data or [],
        "dailyAvailableDays":  len(daily_data) if daily_data else 0,

        "weeklyData":          weekly_data,

        "live7DayMm":          live_7day_mm,
        "live7DayDescription": (
            f"Expected rainfall this week: {live_7day_mm}mm"
            if live_7day_mm is not None else "Live forecast unavailable"
        ),
        "liveDailyForecast":   live_daily,

        "fertilizerCalendar":  get_fertilizer_calendar(annual_mm),
        "cropSuitability":     get_crop_suitability_by_rainfall(annual_mm),
        "risks":               risks,
    })