
import math
import logging

logger = logging.getLogger("soilsense.algorithms")




def forecast_ewma(historical_values: list, alpha: float = 0.3) -> dict:
    """
    Exponential Weighted Moving Average — forecasts next season's annual
    rainfall from a list of past annual values (mm/year).

    Used as fallback when NASA POWER satellite API is unavailable.

    FIX: Previous version calculated trend as ewma[-1] - ewma[-3], which
    measures the EWMA of the EWMA (double-smoothed), not the actual trend
    in the underlying data. This amplified the smoothed trend rather than
    tracking real changes in rainfall.

    Corrected approach:
      - EWMA gives the base level estimate
      - Trend is estimated from the raw data: mean of last 3 years vs
        mean of the 3 years before that
      - Final forecast = EWMA + 0.3 × raw_trend (damped to avoid overfit)
    """
    if not historical_values:
        return {"predicted": 900, "confidence": 50}

    if len(historical_values) < 3:
        avg = sum(historical_values) / len(historical_values)
        return {"predicted": round(avg), "confidence": 55}


    ewma = float(historical_values[0])
    for v in historical_values[1:]:
        ewma = alpha * float(v) + (1 - alpha) * ewma

   
    if len(historical_values) >= 6:
        raw_last3 = sum(historical_values[-3:]) / 3
        raw_prev3 = sum(historical_values[-6:-3]) / 3
        raw_trend = raw_last3 - raw_prev3
    elif len(historical_values) >= 3:
       
        n    = len(historical_values)
        mid  = n // 2
        raw_trend = (sum(historical_values[mid:]) / (n - mid)) - \
                    (sum(historical_values[:mid]) / mid)
    else:
        raw_trend = 0.0

    forecast = max(200, round(ewma + raw_trend * 0.3))

   
    mean       = sum(historical_values) / len(historical_values)
    variance   = sum((v - mean) ** 2 for v in historical_values) / len(historical_values)
    cv         = math.sqrt(variance) / mean if mean > 0 else 0
    confidence = max(50, round(100 - cv * 100))

    return {"predicted": forecast, "confidence": confidence}




def get_rainfall_band(annual_mm: float) -> str:
    """Convert annual rainfall (mm/year) to a band label."""
    if annual_mm < 400:   return "Very Low"
    if annual_mm < 650:   return "Low"
    if annual_mm < 950:   return "Moderate"
    if annual_mm < 1400:  return "High"
    return "Very High"


def get_band_description(annual_mm: float) -> str:
    """Plain-language description of what the annual rainfall band means for a farmer."""
    if annual_mm < 400:
        return (
            "Very dry area (less than 400mm rain per year). "
            "Only grow drought-resistant crops like sorghum or millet. "
            "Consider irrigation."
        )
    if annual_mm < 650:
        return (
            "Dry conditions (400–650mm per year). "
            "Use drought-tolerant crops. Apply fertilizer near the root, not broadcast."
        )
    if annual_mm < 950:
        return (
            "Average rainfall (650–950mm per year). "
            "Good for maize, beans and groundnuts. Standard NPK fertilizer applies."
        )
    if annual_mm < 1400:
        return (
            "Good rainfall (950–1400mm per year). "
            "Maize and rice do well. "
            "Split nitrogen fertilizer into 2–3 applications to prevent leaching."
        )
    return (
        "Very high rainfall (above 1400mm per year). "
        "Use raised beds or ridges to prevent waterlogging. "
        "Split all fertilizer applications."
    )




def get_monthly_distribution(annual_mm: float) -> list:
    """
    Distribute annual rainfall into monthly estimates using Malawi's
    typical seasonal pattern (rainy season: Nov–Apr).
    Returns [{month, mm}] — same format as NASA POWER satellite data
    so the frontend always receives a consistent shape.
    """
    percentages = {
        "Oct": 0.02, "Nov": 0.08, "Dec": 0.14,
        "Jan": 0.20, "Feb": 0.22, "Mar": 0.18,
        "Apr": 0.09, "May": 0.04, "Jun": 0.01,
        "Jul": 0.01, "Aug": 0.00, "Sep": 0.01,
    }
    return [
        {"month": m, "mm": round(annual_mm * frac, 1)}
        for m, frac in percentages.items()
    ]




def get_crop_suitability_by_rainfall(annual_mm: float) -> list:
    """
    Return crops and their suitability score (10–100) for the given
    annual rainfall. Used by the /rainfall endpoint.

    Scoring: crops at the optimal centre of their range score 100.
    At the boundary they score ~70. The half-range is used as the
    denominator so the penalty is proportional to the range width.
    """
    crops = [
        {"crop": "Sorghum",      "min": 300,  "max": 900,  "emoji": "🌾"},
        {"crop": "Millet",       "min": 300,  "max": 800,  "emoji": "🌾"},
        {"crop": "Groundnuts",   "min": 500,  "max": 1200, "emoji": "🥜"},
        {"crop": "Cassava",      "min": 600,  "max": 1500, "emoji": "🍠"},
        {"crop": "Maize",        "min": 600,  "max": 1200, "emoji": "🌽"},
        {"crop": "Beans",        "min": 650,  "max": 1100, "emoji": "🫘"},
        {"crop": "Sweet Potato", "min": 700,  "max": 1300, "emoji": "🍠"},
        {"crop": "Tobacco",      "min": 700,  "max": 1200, "emoji": "🌿"},
        {"crop": "Soybean",      "min": 700,  "max": 1100, "emoji": "🌱"},
        {"crop": "Cotton",       "min": 700,  "max": 1300, "emoji": "🌿"},
        {"crop": "Pigeonpeas",   "min": 600,  "max": 1200, "emoji": "🫘"},
        {"crop": "Cowpea",       "min": 400,  "max": 1000, "emoji": "🫘"},
        {"crop": "Sunflower",    "min": 500,  "max": 1000, "emoji": "🌻"},
        {"crop": "Rice",         "min": 1000, "max": 2500, "emoji": "🍚"},
        {"crop": "Sugarcane",    "min": 1200, "max": 2500, "emoji": "🎋"},
        {"crop": "Tea",          "min": 1200, "max": 2500, "emoji": "🍵"},
        {"crop": "Coffee",       "min": 1000, "max": 2000, "emoji": "☕"},
        {"crop": "Banana",       "min": 900,  "max": 2000, "emoji": "🍌"},
    ]
    result = []
    for c in crops:
        if c["min"] <= annual_mm <= c["max"]:
            centre    = (c["min"] + c["max"]) / 2
            half_range = (c["max"] - c["min"]) / 2
            # FIX: divide by half_range so boundary = 70, centre = 100
            distance  = abs(annual_mm - centre)
            score     = max(10, 100 - round((distance / half_range) * 30))
            result.append({
                "crop":       c["crop"],
                "emoji":      c["emoji"],
                "suitability": score,
            })
    return sorted(result, key=lambda x: -x["suitability"])[:8]




def get_fertilizer_calendar(annual_mm: float) -> list:
    """Seasonal fertilizer calendar based on annual rainfall forecast."""
    if annual_mm < 650:
        return [
            {"month": "November", "action": "Prepare soil. Add compost or manure if available."},
            {"month": "December", "action": "Plant seeds. Use micro-dosing — small amount of fertilizer in each planting hole."},
            {"month": "January",  "action": "Weed carefully. Check for pests."},
            {"month": "February", "action": "Apply small top-dressing only if rain has been steady."},
            {"month": "March",    "action": "Monitor crop. Do not apply fertilizer if soil is dry."},
        ]
    if annual_mm < 950:
        return [
            {"month": "November", "action": "Prepare soil. Add lime if soil is acidic."},
            {"month": "December", "action": "Plant with basal NPK 23:21:0 fertilizer (200 kg/ha)."},
            {"month": "January",  "action": "Weed. Apply Urea top-dressing at 4–6 weeks (100 kg/ha)."},
            {"month": "February", "action": "Check for pests and diseases. Scout fields weekly."},
            {"month": "March",    "action": "Second top-dressing if crop looks pale or yellowish."},
        ]
    return [
        {"month": "November", "action": "Prepare soil. Apply lime if pH is below 6.0."},
        {"month": "December", "action": "Plant with basal NPK 23:21:0 (200 kg/ha). Make ridges to prevent waterlogging."},
        {"month": "January",  "action": "First Urea top-dressing — 50 kg/ha only (split application)."},
        {"month": "February", "action": "Second Urea application 50 kg/ha. Watch for fungal diseases."},
        {"month": "March",    "action": "Do not apply more fertilizer — heavy rain will leach it away."},
    ]




def get_soil_alerts(N: float, P: float, K: float,
                    ph: float, annual_mm: float) -> list:
    """
    Generate plain-language soil health alerts for the farmer.
    Potassium thresholds corrected: < 80 = low, 80–150 = adequate,
    > 300 = excess. Previous version used < 150 as 'low' which was wrong.
    """
    alerts = []

    # pH
    if ph < 5.5:
        alerts.append({
            "type":    "danger",
            "icon":    "⚠️",
            "message": f"Your soil is too acidic (pH {ph}). Apply agricultural lime before planting.",
        })
    elif ph > 8.0:
        alerts.append({
            "type":    "danger",
            "icon":    "⚠️",
            "message": f"Your soil is too alkaline (pH {ph}). Apply sulphur to lower the pH.",
        })
    elif ph < 6.0:
        alerts.append({
            "type":    "warning",
            "icon":    "🟡",
            "message": f"Your soil is slightly acidic (pH {ph}). Add a small amount of lime to improve crop performance.",
        })


    if N < 20:
        alerts.append({
            "type":    "danger",
            "icon":    "⚠️",
            "message": "Nitrogen is very low. Crops will grow slowly and turn yellow. Apply Urea or CAN fertilizer urgently.",
        })
    elif N < 40:
        alerts.append({
            "type":    "warning",
            "icon":    "🟡",
            "message": "Nitrogen is low. Add a nitrogen fertilizer like Urea or CAN before planting.",
        })

   
    if P < 10:
        alerts.append({
            "type":    "danger",
            "icon":    "⚠️",
            "message": "Phosphorus is very low. Crop roots will be weak. Apply DAP fertilizer at planting.",
        })
    elif P < 20:
        alerts.append({
            "type":    "warning",
            "icon":    "🟡",
            "message": "Phosphorus is low. Use DAP or NPK fertilizer at planting.",
        })

   
    if K < 50:
        alerts.append({
            "type":    "danger",
            "icon":    "⚠️",
            "message": f"Potassium is very low ({K:.0f} mg/kg). Crops will be weak and disease-prone. Apply MOP or wood ash urgently.",
        })
    elif K < 80:
        alerts.append({
            "type":    "warning",
            "icon":    "🟡",
            "message": f"Potassium is low ({K:.0f} mg/kg). Apply potassium fertilizer or wood ash before planting.",
        })
    elif K > 300:
        alerts.append({
            "type":    "warning",
            "icon":    "🟡",
            "message": f"Potassium is very high ({K:.0f} mg/kg). Do not add more potassium — excess blocks magnesium uptake.",
        })

   
    if annual_mm < 400:
        alerts.append({
            "type":    "danger",
            "icon":    "🌵",
            "message": "Very low rainfall expected. Only grow sorghum or millet. Consider irrigation.",
        })
    elif annual_mm > 1800:
        alerts.append({
            "type":    "warning",
            "icon":    "🌊",
            "message": "Very heavy rainfall expected. Split fertilizer into small applications to prevent leaching.",
        })

    if not alerts:
        alerts.append({
            "type":    "ok",
            "icon":    "✅",
            "message": "Your soil nutrients are at acceptable levels. Follow the recommended fertilizer plan.",
        })

    return alerts


def assess_soil(N: float, P: float, K: float,
                ph: float, organic_matter: float, moisture: float) -> str:
    """Return a plain-language summary of soil condition."""
    problems = []

    if N < 20:    problems.append("very low nitrogen (crops will turn yellow)")
    elif N < 40:  problems.append("low nitrogen")
    if P < 10:    problems.append("very low phosphorus (weak roots)")
    elif P < 20:  problems.append("low phosphorus")
    if K < 50:    problems.append("very low potassium (disease risk)")
    elif K < 80:  problems.append("low potassium")
    if ph < 5.5:   problems.append("very acidic soil — add lime urgently")
    elif ph > 8.0: problems.append("very alkaline soil — add sulphur")
    elif ph < 6.0: problems.append("slightly acidic soil")
    if organic_matter < 1:   problems.append("very low organic matter — add compost urgently")
    elif organic_matter < 2: problems.append("low organic matter")
    if moisture < 25:  problems.append("dry soil")
    elif moisture > 80: problems.append("waterlogged soil")

    if not problems:
        return "Your soil is in good condition for farming. Follow the recommended fertilizer plan."
    if len(problems) == 1:
        return f"Your soil has one issue: {problems[0]}. Address this before planting."
    return (
        f"Your soil has {len(problems)} issues to fix: "
        f"{'; '.join(problems)}. "
        "Follow the soil improvement advice before planting."
    )




BASE_RATES = {
    "maize":        {"basal_npk": 200, "urea": 100},
    "rice":         {"basal_npk": 150, "urea": 80},
    "wheat":        {"basal_npk": 150, "urea": 100},
    "beans":        {"basal_npk": 100, "urea": 0},
    "kidney beans": {"basal_npk": 100, "urea": 0},
    "kidneybeans":  {"basal_npk": 100, "urea": 0},
    "soybean":      {"basal_npk": 100, "urea": 0},
    "soybeans":     {"basal_npk": 100, "urea": 0},
    "groundnuts":   {"basal_npk": 100, "urea": 0},
    "cassava":      {"basal_npk": 100, "urea": 40},
    "sorghum":      {"basal_npk": 100, "urea": 60},
    "millet":       {"basal_npk": 80,  "urea": 50},
    "cotton":       {"basal_npk": 150, "urea": 120},
    "sugarcane":    {"basal_npk": 200, "urea": 150},
    "tomato":       {"basal_npk": 150, "urea": 80},
    "potato":       {"basal_npk": 200, "urea": 80},
    "sweet potato": {"basal_npk": 100, "urea": 40},
    "sweetpotato":  {"basal_npk": 100, "urea": 40},
    "tobacco":      {"basal_npk": 150, "urea": 100},
    "banana":       {"basal_npk": 180, "urea": 100},
    "coffee":       {"basal_npk": 200, "urea": 120},
    "tea":          {"basal_npk": 200, "urea": 130},
    "pigeon peas":  {"basal_npk": 100, "urea": 0},
    "pigeonpeas":   {"basal_npk": 100, "urea": 0},
    "chickpea":     {"basal_npk": 100, "urea": 0},
    "lentil":       {"basal_npk": 100, "urea": 0},
    "sunflower":    {"basal_npk": 120, "urea": 60},
    "cowpea":       {"basal_npk": 80,  "urea": 0},
    "mungbean":     {"basal_npk": 80,  "urea": 0},
    "blackgram":    {"basal_npk": 80,  "urea": 0},
    "sesame":       {"basal_npk": 80,  "urea": 40},
}

RAINFALL_ADJUSTMENTS = {
    "Very Low": {"npk_factor": 0.6, "urea_factor": 0.5, "split": 1, "method": "micro-dosing"},
    "Low":      {"npk_factor": 0.8, "urea_factor": 0.7, "split": 1, "method": "standard"},
    "Moderate": {"npk_factor": 1.0, "urea_factor": 1.0, "split": 2, "method": "standard"},
    "High":     {"npk_factor": 1.0, "urea_factor": 1.0, "split": 3, "method": "split"},
    "Very High":{"npk_factor": 1.0, "urea_factor": 0.8, "split": 3, "method": "slow-release"},
}


def build_application_plan(npk_rate: int, urea_rate: int, splits: int, method: str) -> list:
    plan = []
    if method == "micro-dosing":
        plan.append({
            "timing": "At planting",
            "action": f"Apply {npk_rate} kg/ha NPK — place in planting hole near seed, not broadcast.",
            "note":   "Micro-dosing conserves fertilizer in dry conditions.",
        })
        if urea_rate > 0:
            plan.append({
                "timing": "4–5 weeks after planting",
                "action": f"Apply {urea_rate} kg/ha Urea — only if rain has fallen that week.",
                "note":   "Never apply Urea to dry soil.",
            })
    elif method == "slow-release":
        plan.append({
            "timing": "At planting",
            "action": f"Apply {npk_rate} kg/ha NPK basal fertilizer.",
            "note":   "Consider slow-release or coated Urea to reduce leaching in very high rainfall.",
        })
        if urea_rate > 0:
            per_split = round(urea_rate / splits)
            for i in range(splits):
                plan.append({
                    "timing": f"Top-dressing {i + 1} — {(i + 1) * 3} weeks after planting",
                    "action": f"Apply {per_split} kg/ha Urea.",
                    "note":   "Small split doses prevent nitrogen washing away in heavy rain.",
                })
    else:
        plan.append({
            "timing": "At planting",
            "action": f"Apply {npk_rate} kg/ha NPK 23:21:0 basal fertilizer.",
            "note":   "Place in planting row or hole, 5 cm from seed.",
        })
        if urea_rate > 0:
            per_split = round(urea_rate / splits)
            for i in range(splits):
                plan.append({
                    "timing": f"Top-dressing {i + 1} — {4 + i * 3} weeks after planting",
                    "action": f"Apply {per_split} kg/ha Urea or CAN.",
                    "note":   "Apply after rain when soil is moist.",
                })
    return plan


def adjust_for_rainfall(annual_mm: float, crop: str) -> dict:
    """
    Generate a rainfall-adjusted fertilizer plan for a crop.
    Used by the /rainfall endpoint.

    FIX: Log a warning when crop is not in BASE_RATES instead of silently
    using a generic plan, so developers can add missing crops.
    """
    crop_key  = crop.lower().strip()
    band      = get_rainfall_band(annual_mm)
    adj       = RAINFALL_ADJUSTMENTS[band]

    if crop_key not in BASE_RATES:
        logger.warning(
            "adjust_for_rainfall: '%s' not in BASE_RATES — using default rates. "
            "Add this crop to BASE_RATES in algorithms.py.",
            crop_key
        )

    rates    = BASE_RATES.get(crop_key, {"basal_npk": 150, "urea": 80})
    npk_rate  = round(rates["basal_npk"] * adj["npk_factor"])
    urea_rate = round(rates["urea"]       * adj["urea_factor"])

    warnings = []
    if annual_mm < 400:
        warnings += [
            "Very low rainfall — irrigation is strongly recommended.",
            "Do not broadcast fertilizer — use micro-dosing only.",
        ]
    if annual_mm > 1400:
        warnings += [
            "High rainfall causes nitrogen leaching. Always split Urea into 2–3 applications.",
            "Watch for fungal diseases in high-moisture conditions.",
        ]
    if band in ("High", "Very High") and crop_key in ("maize", "wheat", "sorghum"):
        warnings.append("Split all Urea applications — never apply the full dose at once.")
    if annual_mm < 600 and crop_key in ("rice", "sugarcane"):
        warnings.append(f"Warning: {crop} normally requires more rainfall than forecast.")

    organic_advice = {
        "Very Low": "Add compost or manure — organic matter holds water in dry soil.",
        "High":     "Add compost to bind nutrients and reduce leaching.",
        "Very High":"Add compost to improve soil structure and bind nutrients.",
    }.get(band, "Add compost or crop residues after harvest to maintain soil organic matter.")

    return {
        "rainfallBand":      band,
        "rainfallMm":        round(annual_mm),
        "basalNpkKgHa":      npk_rate,
        "ureaKgHa":          urea_rate,
        "applicationMethod": adj["method"],
        "splits":            adj["split"],
        "plan":              build_application_plan(npk_rate, urea_rate, adj["split"], adj["method"]),
        "warnings":          warnings,
        "organicAdvice":     organic_advice,
    }


def generate_fertilizer_plan(N: float, P: float, K: float,
                             ph: float, organic_matter: float,
                             rainfall_cat: str) -> list:
    """
    Generate a deficiency-based fertilizer plan from soil test values.
    Called from the /recommend endpoint for soil-specific advice.

    FIX: Replaced TSP (0-46-0) with DAP (18:46:0) — TSP has negligible
    import volumes in Malawi per FAO FertilizersProduct data. DAP is
    the practical phosphorus source actually available to Malawi farmers.
    """
    plans    = []
    adj_note = ""
    if rainfall_cat in ("High", "Very High"):
        adj_note = "Split application recommended in high rainfall zone."
    elif rainfall_cat in ("Low", "Very Low"):
        adj_note = "Apply near root zone — not broadcast — in dry conditions."

    if N < 60:
        plans.append({
            "type":            "Urea (46-0-0)",
            "applicationRate": f"{round((60 - N) * 2.2)} kg/ha",
            "timing":          "Basal + top-dress at 4–6 weeks after planting",
            "notes":           f"Nitrogen deficient. {adj_note}",
        })

    if P < 30:
    
        plans.append({
            "type":            "DAP (18:46:0)",
            "applicationRate": f"{round((30 - P) * 2.5)} kg/ha",
            "timing":          "Basal at planting",
            "notes":           "Phosphorus boost for root development and nodulation.",
        })

    
    if K < 80:
        plans.append({
            "type":            "MOP (0-0-60)",
            "applicationRate": f"{round((80 - K) * 1.8)} kg/ha",
            "timing":          "Basal at planting",
            "notes":           "Potassium for disease resistance and water uptake.",
        })

    if N >= 60 and P >= 30 and K >= 80:
        plans.append({
            "type":            "NPK 23:21:0 (Maintenance)",
            "applicationRate": "100 kg/ha",
            "timing":          "Basal at planting",
            "notes":           "Maintenance dose — soil nutrients are at adequate levels.",
        })

    if organic_matter < 2:
        plans.append({
            "type":            "Compost / Manure",
            "applicationRate": "5–10 tonnes/ha",
            "timing":          "2–4 weeks before planting",
            "notes":           "Low organic matter reduces water retention and microbial activity.",
        })

    if ph < 5.5:
        plans.append({
            "type":            "Agricultural Lime",
            "applicationRate": f"{round((5.5 - ph) * 2000)} kg/ha",
            "timing":          "4–6 weeks before planting",
            "notes":           "Correct soil acidity before applying any other fertilizer.",
        })

    return plans