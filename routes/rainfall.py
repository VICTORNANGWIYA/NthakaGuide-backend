from flask import Blueprint, request, jsonify
import logging

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
    SEASON_CACHE_TIMEOUT,
)
from utils.season_helper import (
    get_season_label,
    get_weekly_summary,
    estimate_season_total,
)

from extensions.cache_ext import cache                    # ← no circular import

rainfall_bp = Blueprint("rainfall", __name__)
logger = logging.getLogger("NthakaGuide.rainfall")


def _cache_key(prefix: str, lat: float, lon: float) -> str:
    return f"{prefix}_{lat}_{lon}"


def _get_annual_history(lat: float, lon: float) -> dict | None:
    key  = _cache_key("nasa_history", lat, lon)
    hist = cache.get(key)

    if hist is not None:
        logger.info(
            "Annual history cache HIT for lat=%.4f lon=%.4f "
            "(expires in ~%d hours)",
            lat, lon, SEASON_CACHE_TIMEOUT // 3600,
        )
        return hist

    logger.info(
        "Annual history cache MISS for lat=%.4f lon=%.4f — "
        "fetching from NASA (this may take ~30–60 seconds) …",
        lat, lon,
    )
    hist = get_satellite_annual_history(lat, lon)

    if hist:
        cache.set(key, hist, timeout=SEASON_CACHE_TIMEOUT)
        logger.info(
            "Annual history cached for lat=%.4f lon=%.4f — "
            "will be served from cache for the rest of this season.",
            lat, lon,
        )

    return hist


def _get_monthly(lat: float, lon: float) -> dict | None:
    key  = _cache_key("nasa_monthly", lat, lon)
    data = cache.get(key)

    if data is not None:
        logger.info("Monthly cache HIT for lat=%.4f lon=%.4f", lat, lon)
        return data

    data = get_satellite_monthly(lat, lon)

    if data:
        cache.set(key, data, timeout=7 * 24 * 3600)
        logger.info("Monthly data cached for lat=%.4f lon=%.4f", lat, lon)

    return data


def _get_daily(lat: float, lon: float) -> dict | None:
    key  = _cache_key("nasa_daily", lat, lon)
    data = cache.get(key)

    if data is not None:
        logger.info("Daily cache HIT for lat=%.4f lon=%.4f", lat, lon)
        return data

    data = get_satellite_daily(lat, lon, days=30)

    if data:
        cache.set(key, data, timeout=6 * 3600)
        logger.info("Daily data cached for lat=%.4f lon=%.4f", lat, lon)

    return data


@rainfall_bp.route("/rainfall", methods=["POST"])
def rainfall():

    body          = request.get_json(silent=True) or {}
    district_name = body.get("districtName")

    if not district_name:
        return jsonify({"error": "Missing districtName"}), 400

    if district_name not in DISTRICT_COORDINATES:
        return jsonify({
            "error": f"District '{district_name}' has no coordinates "
                     f"configured. Cannot fetch satellite rainfall data."
        }), 400

    coords     = DISTRICT_COORDINATES[district_name]
    lat, lon   = coords[0], coords[1]
    avg_annual = DISTRICT_DEFAULTS.get(district_name, 900)
    season     = get_season_label()

    live_7day_mm = None
    live_daily   = None
    live = get_live_rainfall(lat, lon)
    if live:
        live_7day_mm = live["total_mm"]
        live_daily   = live["daily_forecast"]
    else:
        logger.warning("Live 7-day forecast unavailable for %s", district_name)

    historical_years  = []
    historical_values = []
    annual_mm         = None
    annual_confidence = None
    annual_source     = None

    hist = _get_annual_history(lat, lon)
    if hist:
        historical_years  = hist["years"]
        historical_values = hist["values"]
        annual_mm         = hist["annual_mm"]
        annual_confidence = 85
        annual_source     = (
            f"NASA POWER Satellite ({historical_years[0]}–{historical_years[-1]})"
            if historical_years else "NASA POWER Satellite"
        )
    else:
        logger.warning(
            "NASA POWER annual history unavailable for %s — falling back (%dmm)",
            district_name, avg_annual,
        )
        annual_mm         = avg_annual
        annual_confidence = 55
        annual_source     = "District Historical Average (NASA unavailable)"

    monthly_data   = None
    monthly_source = None

    m = _get_monthly(lat, lon)
    if m:
        monthly_data   = m["monthly"]
        monthly_source = "NASA POWER Satellite"
    else:
        logger.warning("NASA POWER monthly data unavailable for %s", district_name)

    if monthly_data:
        monthly_distribution = [{"month": i["month"], "mm": i["mm"]} for i in monthly_data]
    else:
        monthly_distribution = get_monthly_distribution(annual_mm)
        monthly_source       = "Computed from annual forecast"

    daily_data  = None
    weekly_data = []

    d = _get_daily(lat, lon)
    if d:
        daily_data  = d["daily"]
        weekly_data = get_weekly_summary(daily_data)
    else:
        logger.warning("NASA POWER daily data unavailable for %s", district_name)

    season_totals = estimate_season_total(monthly_distribution, annual_mm)
    band          = get_rainfall_band(annual_mm)

    risks          = []
    below_avg_warn = False

    if band == "Very High":
        risks.append({"level": "danger", "icon": "🌊", "message": f"Very heavy rainfall expected ({annual_mm:,}mm/yr). Build drainage ridges to prevent waterlogging and crop loss."})
    elif band == "High":
        risks.append({"level": "warning", "icon": "🌊", "message": f"High rainfall expected ({annual_mm:,}mm/yr). Split nitrogen fertilizer into 2–3 applications to reduce leaching."})
    elif band == "Very Low":
        risks.append({"level": "danger", "icon": "🌵", "message": f"Very low rainfall expected ({annual_mm:,}mm/yr). Only grow drought-tolerant crops: sorghum, millet, cowpea. Consider supplementary irrigation."})
        below_avg_warn = True
    elif band == "Low":
        risks.append({"level": "warning", "icon": "🌵", "message": f"Low rainfall expected ({annual_mm:,}mm/yr). Use drought-tolerant varieties and apply mulch to conserve moisture."})
        below_avg_warn = True

    if not below_avg_warn and annual_mm < avg_annual * 0.85:
        risks.append({"level": "warning", "icon": "📉", "message": f"Below-average rainfall forecast ({annual_mm:,}mm vs usual {avg_annual:,}mm). Plan for possible mid-season dry spells."})

    if not risks:
        risks.append({"level": "ok", "icon": "✅", "message": "Rainfall outlook is normal. Good conditions for most crops."})

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
        "monthlySource":       monthly_source,
        "dailyData":           daily_data or [],
        "dailyAvailableDays":  len(daily_data) if daily_data else 0,
        "weeklyData":          weekly_data,
        "live7DayMm":          live_7day_mm,
        "live7DayDescription": f"Expected rainfall this week: {live_7day_mm}mm" if live_7day_mm is not None else "Live forecast unavailable",
        "liveDailyForecast":   live_daily,
        "fertilizerCalendar":  get_fertilizer_calendar(annual_mm),
        "cropSuitability":     get_crop_suitability_by_rainfall(annual_mm),
        "risks":               risks,
    })