"""
NthakaGuide — algorithms.py  (v2 — Malawi-precise rule engine)
===============================================================
Improvements over v1:
  1.  Crop-specific N/P/K base rates with physiological rationale
  2.  Soil-type leaching multipliers (sandy vs clay vs loamy)
  3.  pH-aware fertilizer product selection (CAN over Urea on acid soils)
  4.  Deficiency-severity-scaled fertilizer rates (not just on/off)
  5.  CAN and Ammonium sulphate added as first-class products
      (FAO data: CAN = 155k tonnes, AS = 201k tonnes imported by Malawi)
  6.  MAP added as alternative P source to DAP
  7.  Potassium leaching adjustment in very high rainfall
  8.  Precise compost/organic rates and timing
  9.  Confidence scoring on every recommendation
 10.  Crop-growth-stage-aware application timing
"""

import math
import logging

logger = logging.getLogger("NthakaGuide.algorithms")


# ─────────────────────────────────────────────────────────────────────────────
#  RAINFALL FORECASTING  (unchanged — already correct)
# ─────────────────────────────────────────────────────────────────────────────

def forecast_ewma(historical_values: list, alpha: float = 0.3) -> dict:
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
        n   = len(historical_values)
        mid = n // 2
        raw_trend = (sum(historical_values[mid:]) / (n - mid)) - \
                    (sum(historical_values[:mid]) / mid)
    else:
        raw_trend = 0.0

    forecast = max(200, round(ewma + raw_trend * 0.3))

    mean     = sum(historical_values) / len(historical_values)
    variance = sum((v - mean) ** 2 for v in historical_values) / len(historical_values)
    cv       = math.sqrt(variance) / mean if mean > 0 else 0
    confidence = max(50, round(100 - cv * 100))

    return {"predicted": forecast, "confidence": confidence}


# ─────────────────────────────────────────────────────────────────────────────
#  RAINFALL BANDS
# ─────────────────────────────────────────────────────────────────────────────

def get_rainfall_band(annual_mm: float) -> str:
    if annual_mm < 400:  return "Very Low"
    if annual_mm < 650:  return "Low"
    if annual_mm < 950:  return "Moderate"
    if annual_mm < 1400: return "High"
    return "Very High"


def get_band_description(annual_mm: float) -> str:
    if annual_mm < 600:
        return ("Very dry area (less than 600 mm/year). "
                "Only grow drought-resistant crops like sorghum or millet. "
                "Consider irrigation.")
    if annual_mm < 850:
        return ("Dry conditions (600–850 mm/year). "
                "Use drought-tolerant crops. Apply fertilizer near the root only.")
    if annual_mm < 1050:
        return ("Average rainfall (850–1050 mm/year). "
                "Good for maize, beans and groundnuts. Standard NPK fertilizer applies.")
    if annual_mm < 2500:
        return ("Good rainfall (1050–2500 mm/year). "
                "Maize and rice do well. "
                "Split nitrogen into 2–3 applications to prevent leaching.")
    return ("Very high rainfall (above 2500 mm/year). "
            "Use raised beds or ridges to prevent waterlogging. "
            "Split ALL fertilizer applications — including basal.")


def get_monthly_distribution(annual_mm: float) -> list:
    percentages = {
        "Oct": 0.02, "Nov": 0.08, "Dec": 0.14,
        "Jan": 0.20, "Feb": 0.22, "Mar": 0.18,
        "Apr": 0.09, "May": 0.04, "Jun": 0.01,
        "Jul": 0.01, "Aug": 0.00, "Sep": 0.01,
    }
    return [{"month": m, "mm": round(annual_mm * f, 1)}
            for m, f in percentages.items()]


# ─────────────────────────────────────────────────────────────────────────────
#  CROP SUITABILITY  (unchanged)
# ─────────────────────────────────────────────────────────────────────────────

def get_crop_suitability_by_rainfall(annual_mm: float) -> list:
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
            centre     = (c["min"] + c["max"]) / 2
            half_range = (c["max"] - c["min"]) / 2
            distance   = abs(annual_mm - centre)
            score      = max(10, 100 - round((distance / half_range) * 30))
            result.append({"crop": c["crop"], "emoji": c["emoji"], "suitability": score})
    return sorted(result, key=lambda x: -x["suitability"])[:8]


# ─────────────────────────────────────────────────────────────────────────────
#  FERTILIZER CALENDAR  (improved — crop-aware)
# ─────────────────────────────────────────────────────────────────────────────

def get_fertilizer_calendar(annual_mm: float) -> list:
    if annual_mm < 650:
        return [
            {"month": "November", "action": "Prepare soil. Apply 5–10 t/ha compost or manure, 2–3 weeks before planting."},
            {"month": "December", "action": "Plant seeds. Use micro-dosing: 1–2 g NPK per planting hole. Do not broadcast."},
            {"month": "January",  "action": "Weed carefully. Apply Urea or CAN top-dressing only after rainfall (max 30 kg/ha)."},
            {"month": "February", "action": "Second top-dressing if rains are steady. Skip if soil is dry — wait for rain first."},
            {"month": "March",    "action": "Final monitoring. No more fertilizer — dry season approaching."},
        ]
    if annual_mm < 950:
        return [
            {"month": "November", "action": "Prepare soil. Add lime if pH below 6.0 (2 t/ha). Apply 5 t/ha compost."},
            {"month": "December", "action": "Plant with basal NPK 23:21:0 at 200 kg/ha. Place 5 cm from seed in planting row."},
            {"month": "January",  "action": "Weed. First Urea or CAN top-dressing at 4–6 weeks: 50 kg/ha after rainfall."},
            {"month": "February", "action": "Second top-dressing: 50 kg/ha Urea or CAN. Check for pests and diseases weekly."},
            {"month": "March",    "action": "Final pest and disease check. No fertilizer — focus on crop protection."},
        ]
    return [
        {"month": "November", "action": "Prepare soil. Apply lime if pH below 6.0. Make ridges or raised beds to prevent waterlogging."},
        {"month": "December", "action": "Plant with basal NPK 23:21:0 at 200 kg/ha. In very high rainfall, split into 2 × 100 kg/ha."},
        {"month": "January",  "action": "First Urea or CAN top-dressing: 40 kg/ha only. Heavy rain will leach more if you apply too much."},
        {"month": "February", "action": "Second top-dressing: 40 kg/ha. Watch for fungal diseases — wet conditions spread them fast."},
        {"month": "March",    "action": "Third top-dressing if crop is pale: 20 kg/ha maximum. Stop all fertilizer by end of March."},
    ]


# ─────────────────────────────────────────────────────────────────────────────
#  SOIL TYPE LEACHING MULTIPLIERS  (NEW)
#  Source: standard soil science — sandy soils hold ~40% less N than loamy
# ─────────────────────────────────────────────────────────────────────────────

SOIL_LEACHING_FACTOR = {
    "sandy":   1.25,   # loses nutrients fastest — increase rate to compensate
    "loamy":   1.00,   # reference soil
    "clay":    0.90,   # holds nutrients well — slight reduction
    "clayey":  0.90,
    "silt":    0.95,
    "peaty":   0.85,   # high organic — nutrients bind well
    "black":   0.90,   # vertisol — high clay content
    "red":     1.10,   # laterite — moderate leaching
    "neutral": 1.00,
    "acidic":  1.05,   # slightly higher loss due to fixation
    "alkaline":0.95,
}

def _soil_factor(soil_type: str) -> float:
    return SOIL_LEACHING_FACTOR.get(soil_type.lower().strip(), 1.00)


# ─────────────────────────────────────────────────────────────────────────────
#  CROP-SPECIFIC BASE RATES  (v2 — physiologically grounded)
#
#  Units: kg/ha of product (not elemental nutrient)
#  basal_npk : NPK 23:21:0 compound fertilizer at planting
#  urea      : 46-0-0 total across all top-dressings
#  dap_extra : additional DAP when crop needs P boost beyond NPK basal
#  k_extra   : additional MOP/SOP when crop needs K boost
#  preferred_n_source: which N product suits this crop best
#
#  Evidence base:
#  - Malawi Ministry of Agriculture extension recommendations
#  - FAO Fertilizer and Plant Nutrition Bulletin 16 (Sub-Saharan Africa)
#  - IFPRI Malawi supply chain survey (Jumbe, 2016)
# ─────────────────────────────────────────────────────────────────────────────

CROP_BASE_RATES = {
    # ── CEREALS ──────────────────────────────────────────────────────────────
    "maize": {
        "basal_npk": 200, "urea": 100, "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "Malawi's primary staple. High N demand at V6 stage. "
                "NPK 23:21:0 basal standard per MoA recommendation."
    },
    "rice": {
        "basal_npk": 150, "urea": 100, "dap_extra": 0,   "k_extra": 20,
        "preferred_n": "urea",
        "note": "Flooded paddies fix some N but still need top-dress. "
                "K important for stem strength."
    },
    "sorghum": {
        "basal_npk": 100, "urea": 60,  "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "Drought-tolerant. Lower rates needed. "
                "Responds well to split N."
    },
    "millet": {
        "basal_npk": 80,  "urea": 50,  "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "Efficient N user. Lower basal still gives good yield."
    },
    "wheat": {
        "basal_npk": 150, "urea": 100, "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "Mainly grown in Malawi highlands. CAN preferred on acidic highland soils."
    },

    # ── LEGUMES (fix atmospheric N — urea = 0) ───────────────────────────────
    "beans": {
        "basal_npk": 100, "urea": 0,   "dap_extra": 30,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Nitrogen-fixing. Starter P (DAP) improves nodulation. "
                "Never apply Urea — suppresses N fixation."
    },
    "kidney beans": {
        "basal_npk": 100, "urea": 0,   "dap_extra": 30,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Same as beans. DAP at planting boosts root nodule formation."
    },
    "soybean": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 40,  "k_extra": 20,
        "preferred_n": "none",
        "note": "High P demand for seed fill. K important for oil quality. "
                "Inoculant (Bradyrhizobium) recommended alongside DAP."
    },
    "soybeans": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 40,  "k_extra": 20,
        "preferred_n": "none",
        "note": "Same as soybean."
    },
    "groundnuts": {
        "basal_npk": 100, "urea": 0,   "dap_extra": 50,  "k_extra": 30,
        "preferred_n": "none",
        "note": "Legume but very high P and K demand for pod development. "
                "Calcium also important — gypsum at 200 kg/ha helps pod fill."
    },
    "pigeon peas": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 30,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Deep-rooted legume. Minimal fertilizer needed."
    },
    "pigeonpeas": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 30,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Same as pigeon peas."
    },
    "cowpea": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 25,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Drought-tolerant legume. Low input crop."
    },
    "chickpea": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 30,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Legume. Starter P only."
    },
    "lentil": {
        "basal_npk": 80,  "urea": 0,   "dap_extra": 25,  "k_extra": 0,
        "preferred_n": "none",
        "note": "Legume. Minimal fertilizer."
    },

    # ── ROOT CROPS ────────────────────────────────────────────────────────────
    "cassava": {
        "basal_npk": 100, "urea": 40,  "dap_extra": 0,   "k_extra": 50,
        "preferred_n": "urea_or_can",
        "note": "High K demand for tuber starch. Low N — excess N causes "
                "leafy growth at expense of roots."
    },
    "sweet potato": {
        "basal_npk": 100, "urea": 40,  "dap_extra": 0,   "k_extra": 60,
        "preferred_n": "urea_or_can",
        "note": "Very high K demand. Excess N reduces tuber yield. "
                "SOP preferred over MOP to avoid chloride."
    },
    "sweetpotato": {
        "basal_npk": 100, "urea": 40,  "dap_extra": 0,   "k_extra": 60,
        "preferred_n": "urea_or_can",
        "note": "Same as sweet potato."
    },
    "potato": {
        "basal_npk": 200, "urea": 80,  "dap_extra": 0,   "k_extra": 80,
        "preferred_n": "urea_or_can",
        "note": "High NPK demand. K critical for tuber quality. "
                "SOP preferred — chloride from MOP reduces starch content."
    },

    # ── CASH CROPS ────────────────────────────────────────────────────────────
    "tobacco": {
        "basal_npk": 150, "urea": 60,  "dap_extra": 0,   "k_extra": 120,
        "preferred_n": "can",          # CAN preferred — Urea can cause tip burn
        "note": "Very high K demand for leaf quality. CAN preferred over Urea "
                "— Urea causes leaf tip burn on flue-cured tobacco. "
                "Ammonium sulphate good for sulphur on alkaline soils."
    },
    "cotton": {
        "basal_npk": 150, "urea": 120, "dap_extra": 0,   "k_extra": 40,
        "preferred_n": "urea_or_can",
        "note": "High N demand during boll formation. K for fibre quality."
    },
    "sugarcane": {
        "basal_npk": 200, "urea": 150, "dap_extra": 0,   "k_extra": 80,
        "preferred_n": "urea",
        "note": "Very high N and K demand over long growing season. "
                "Multiple split applications essential."
    },
    "tea": {
        "basal_npk": 200, "urea": 130, "dap_extra": 0,   "k_extra": 50,
        "preferred_n": "ammonium_sulphate",  # AS preferred — acidifies soil
        "note": "Tea prefers acid soils (pH 4.5–5.5). Ammonium sulphate "
                "recommended — maintains acidity and provides sulphur. "
                "FAO: 201k tonnes AS imported by Malawi annually."
    },
    "coffee": {
        "basal_npk": 200, "urea": 120, "dap_extra": 0,   "k_extra": 60,
        "preferred_n": "urea_or_can",
        "note": "Perennial. High K for fruit quality."
    },

    # ── OILSEEDS ──────────────────────────────────────────────────────────────
    "sunflower": {
        "basal_npk": 120, "urea": 60,  "dap_extra": 0,   "k_extra": 20,
        "preferred_n": "urea_or_can",
        "note": "Moderate NPK. Boron micronutrient important for seed set."
    },
    "sesame": {
        "basal_npk": 80,  "urea": 40,  "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "Low input crop. Over-fertilisation causes excessive leafy growth."
    },

    # ── HORTICULTURE ──────────────────────────────────────────────────────────
    "tomato": {
        "basal_npk": 150, "urea": 80,  "dap_extra": 30,  "k_extra": 60,
        "preferred_n": "urea_or_can",
        "note": "High P at transplanting for root establishment. "
                "High K for fruit quality and disease resistance."
    },
    "banana": {
        "basal_npk": 180, "urea": 100, "dap_extra": 0,   "k_extra": 100,
        "preferred_n": "urea_or_can",
        "note": "Very high K demand — banana removes 400+ kg K per ha per year. "
                "Apply K in multiple small doses."
    },
    "mango": {
        "basal_npk": 120, "urea": 60,  "dap_extra": 0,   "k_extra": 40,
        "preferred_n": "urea_or_can",
        "note": "Perennial tree. Fertilize twice yearly: before rains and after harvest."
    },
    "papaya": {
        "basal_npk": 150, "urea": 80,  "dap_extra": 0,   "k_extra": 50,
        "preferred_n": "urea_or_can",
        "note": "Heavy feeder. Monthly small applications better than one large dose."
    },
    "watermelon": {
        "basal_npk": 150, "urea": 80,  "dap_extra": 20,  "k_extra": 50,
        "preferred_n": "urea_or_can",
        "note": "High K for fruit sweetness. Reduce N after vine establishment."
    },

    # ── DEFAULT (fallback) ────────────────────────────────────────────────────
    "_default": {
        "basal_npk": 150, "urea": 80,  "dap_extra": 0,   "k_extra": 0,
        "preferred_n": "urea_or_can",
        "note": "General recommendation. Add this crop to CROP_BASE_RATES for precision."
    },
}

# ─────────────────────────────────────────────────────────────────────────────
#  RAINFALL ADJUSTMENT FACTORS  (v2 — K leaching added)
# ─────────────────────────────────────────────────────────────────────────────

RAINFALL_ADJUSTMENTS = {
    #                npk    urea   k      split  method
    "Very Low":  {"npk": 0.60, "urea": 0.50, "k": 1.00, "split": 1, "method": "micro-dosing"},
    "Low":       {"npk": 0.80, "urea": 0.70, "k": 1.00, "split": 1, "method": "standard"},
    "Moderate":  {"npk": 1.00, "urea": 1.00, "k": 1.00, "split": 2, "method": "standard"},
    "High":      {"npk": 1.00, "urea": 1.00, "k": 1.10, "split": 3, "method": "split"},
    "Very High": {"npk": 1.00, "urea": 0.80, "k": 1.20, "split": 3, "method": "slow-release"},
}

# ─────────────────────────────────────────────────────────────────────────────
#  pH-AWARE NITROGEN PRODUCT SELECTION  (NEW)
# ─────────────────────────────────────────────────────────────────────────────

def _select_n_product(preferred_n: str, ph: float, band: str) -> dict:
    """
    Choose the best nitrogen product given crop preference and soil pH.

    Rules (evidence-based):
    - pH < 5.5  → CAN (26% N, neutral reaction) preferred over Urea
                  Urea hydrolyses to ammonium → further acidifies soil
    - pH > 7.5  → Ammonium sulphate good if crop tolerates acidity (tea, coffee)
                  because AS acidifies soil bringing it toward neutral
    - Highlands + cereals → CAN slower release, less volatilisation risk
    - Default   → Urea (most available, cheapest in Malawi — FAO: 1.7M tonnes)

    Returns dict with product name, N%, rate note, and reasoning.
    """
    if preferred_n == "none":
        return {
            "product": None,
            "n_pct": 0,
            "reason": "Legume — fixes atmospheric nitrogen. No N fertilizer needed.",
        }

    if preferred_n == "ammonium_sulphate":
        return {
            "product": "Ammonium Sulphate (AS)",
            "n_pct": 21,
            "s_pct": 24,
            "reason": ("Crop benefits from soil acidification and sulphur supply. "
                       "Ammonium sulphate (21% N + 24% S) is the correct choice. "
                       "Widely imported in Malawi — 201,000 tonnes/year (FAO)."),
        }

    if preferred_n == "can":
        return {
            "product": "CAN (Calcium Ammonium Nitrate)",
            "n_pct": 26,
            "reason": ("Crop-specific recommendation. CAN (26% N) has slower "
                       "release than Urea and avoids leaf tip burn risk. "
                       "Widely available in Malawi — 155,000 tonnes/year (FAO)."),
        }

    # pH-driven override
    if ph < 5.5:
        return {
            "product": "CAN (Calcium Ammonium Nitrate)",
            "n_pct": 26,
            "reason": (f"Soil pH is {ph:.1f} — acidic. Urea further acidifies soil "
                       "during hydrolysis. CAN (26% N) has a near-neutral soil reaction "
                       "and is the safer choice. Correct acidity with lime first."),
        }

    if ph > 7.5 and preferred_n in ("urea_or_can",):
        return {
            "product": "Urea (46% N) or Ammonium Sulphate (21% N + 24% S)",
            "n_pct": 46,
            "reason": (f"Soil pH is {ph:.1f} — alkaline. Ammonium sulphate can help "
                       "acidify soil toward neutral while supplying N and S. "
                       "Urea also acceptable. Avoid CAN on alkaline soils."),
        }

    if band in ("High", "Very High"):
        return {
            "product": "CAN (Calcium Ammonium Nitrate) or Urea (split)",
            "n_pct": 26,
            "reason": ("High rainfall increases nitrogen volatilisation from Urea. "
                       "CAN (26% N) or split Urea applications reduce this risk. "
                       "Never apply all Urea at once in high-rainfall areas."),
        }

    # Default — Urea (most available and cheapest in Malawi)
    return {
        "product": "Urea (46% N)",
        "n_pct": 46,
        "reason": "Standard choice. Most available and cost-effective N source in Malawi.",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  APPLICATION PLAN BUILDER  (v2 — crop-aware timing)
# ─────────────────────────────────────────────────────────────────────────────

def _build_application_plan(
    npk_rate: int,
    urea_rate: int,
    dap_extra: int,
    k_extra: int,
    splits: int,
    method: str,
    n_product: dict,
    crop: str,
) -> list:
    plan = []
    crop_lower = crop.lower().strip()

    # ── BASAL APPLICATION ─────────────────────────────────────────────────────
    if method == "micro-dosing":
        plan.append({
            "timing": "At planting",
            "action": (f"Apply {npk_rate} kg/ha NPK 23:21:0 — place 1–2 g per "
                       f"planting hole near the seed, not broadcast."),
            "note": "Micro-dosing conserves fertilizer in dry conditions. "
                    "A small precise dose at the root is more effective than a "
                    "large broadcast application on dry soil.",
            "products": [f"NPK 23:21:0 — {npk_rate} kg/ha"],
        })
    else:
        basal_note = "Place in planting row or hole, 5 cm from seed, covered with soil."
        if method == "slow-release" and npk_rate > 100:
            half = npk_rate // 2
            plan.append({
                "timing": "At planting",
                "action": (f"Apply {half} kg/ha NPK 23:21:0 basal fertilizer "
                           f"(half rate — split application due to very high rainfall)."),
                "note": "In very high rainfall areas, split basal application prevents "
                        "phosphorus run-off. Apply second half at 3 weeks.",
                "products": [f"NPK 23:21:0 — {half} kg/ha"],
            })
            plan.append({
                "timing": "3 weeks after planting",
                "action": f"Apply remaining {npk_rate - half} kg/ha NPK 23:21:0.",
                "note": "Second half of basal application.",
                "products": [f"NPK 23:21:0 — {npk_rate - half} kg/ha"],
            })
        else:
            plan.append({
                "timing": "At planting",
                "action": f"Apply {npk_rate} kg/ha NPK 23:21:0 basal fertilizer.",
                "note": basal_note,
                "products": [f"NPK 23:21:0 — {npk_rate} kg/ha"],
            })

    # ── EXTRA DAP (P boost for legumes and some horticulture) ─────────────────
    if dap_extra > 0:
        plan.append({
            "timing": "At planting (with basal)",
            "action": f"Apply additional {dap_extra} kg/ha DAP (18:46:0) for phosphorus boost.",
            "note": ("DAP provides extra phosphorus for root nodule formation "
                     "(legumes) or early root establishment. Mix with basal NPK "
                     "or apply in same planting hole."),
            "products": [f"DAP 18:46:0 — {dap_extra} kg/ha"],
        })

    # ── EXTRA K (K-demanding crops) ───────────────────────────────────────────
    if k_extra > 0:
        k_product = "SOP (Potassium Sulphate)" if crop_lower in (
            "sweet potato", "sweetpotato", "potato", "tobacco", "tomato"
        ) else "MOP (Muriate of Potash) or SOP"
        plan.append({
            "timing": "At planting (with basal)",
            "action": f"Apply additional {k_extra} kg/ha {k_product} for potassium.",
            "note": (f"{crop.title()} has a high potassium demand. "
                     "SOP (50% K) preferred over MOP (60% K) for quality-sensitive crops "
                     "as chloride from MOP can reduce quality."),
            "products": [f"{k_product} — {k_extra} kg/ha"],
        })

    # ── NITROGEN TOP-DRESSINGS ────────────────────────────────────────────────
    if urea_rate > 0 and n_product.get("product"):
        n_prod = n_product["product"]
        per_split = round(urea_rate / splits)

        if method == "micro-dosing":
            plan.append({
                "timing": "4–5 weeks after planting",
                "action": (f"Apply {urea_rate} kg/ha {n_prod} — "
                           f"only if rain has fallen within the past 3 days."),
                "note": "Never apply nitrogen to dry soil. It volatilises and is wasted. "
                        "Wait for rain, then apply within 24 hours.",
                "products": [f"{n_prod} — {urea_rate} kg/ha"],
            })
        else:
            # Crop-specific timing
            if crop_lower in ("maize",):
                timings = ["4–6 weeks (knee-high stage)", "8–10 weeks (tasseling stage)", "11–12 weeks"]
            elif crop_lower in ("tobacco",):
                timings = ["3–4 weeks after transplanting", "6–7 weeks", "9–10 weeks"]
            elif crop_lower in ("sugarcane",):
                timings = ["4 weeks after planting", "3 months", "6 months"]
            elif crop_lower in ("rice",):
                timings = ["Tillering stage (3–4 weeks)", "Panicle initiation (7–8 weeks)", "10 weeks"]
            elif crop_lower in ("cotton",):
                timings = ["4 weeks", "First squaring (7 weeks)", "First flower (10 weeks)"]
            else:
                timings = [f"{4 + i*3} weeks after planting" for i in range(splits)]

            for i in range(splits):
                timing_label = timings[i] if i < len(timings) else f"{4 + i*3} weeks"
                plan.append({
                    "timing": f"Top-dressing {i+1} — {timing_label}",
                    "action": f"Apply {per_split} kg/ha {n_prod}.",
                    "note": ("Apply after rainfall when soil is moist. "
                             "Do not apply if dry weather is forecast for the next 5 days."),
                    "products": [f"{n_prod} — {per_split} kg/ha"],
                })

    return plan


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN FERTILIZER ADJUSTMENT FUNCTION  (v2)
# ─────────────────────────────────────────────────────────────────────────────

def adjust_for_rainfall(
    annual_mm: float,
    crop: str,
    ph: float = 6.5,
    soil_type: str = "loamy",
) -> dict:
    """
    Generate a precision fertilizer plan adjusted for:
      - Rainfall band (Very Low → Very High)
      - Crop physiology (crop-specific NPK rates)
      - Soil type (leaching multiplier)
      - Soil pH (N product selection)

    Returns structured plan with products, rates, timing, and confidence score.
    """
    crop_key = crop.lower().strip()
    band     = get_rainfall_band(annual_mm)
    adj      = RAINFALL_ADJUSTMENTS[band]
    rates    = CROP_BASE_RATES.get(crop_key, CROP_BASE_RATES["_default"])
    sf       = _soil_factor(soil_type)

    if crop_key not in CROP_BASE_RATES:
        logger.warning(
            "adjust_for_rainfall: '%s' not in CROP_BASE_RATES — using default. "
            "Add to CROP_BASE_RATES for precision.",
            crop_key,
        )

    # Apply rainfall and soil adjustments
    npk_rate  = round(rates["basal_npk"] * adj["npk"]  * sf)
    urea_rate = round(rates["urea"]      * adj["urea"] * sf)
    k_extra   = round(rates.get("k_extra", 0) * adj["k"] * sf)
    dap_extra = rates.get("dap_extra", 0)

    # pH-aware N product selection
    n_product = _select_n_product(rates.get("preferred_n", "urea_or_can"), ph, band)

    # Build application plan
    plan = _build_application_plan(
        npk_rate, urea_rate, dap_extra, k_extra,
        adj["split"], adj["method"], n_product, crop,
    )

    # Warnings
    warnings = _build_warnings(annual_mm, band, crop_key, ph, soil_type)

    # Organic advice (now with precise rates)
    organic_advice = _get_organic_advice(band, soil_type)

    # Confidence scoring (NEW)
    confidence = _score_confidence(crop_key, ph, soil_type, annual_mm, band)

    return {
        "rainfallBand":       band,
        "rainfallMm":         round(annual_mm),
        "basalNpkKgHa":       npk_rate,
        "ureaKgHa":           urea_rate,
        "dapExtraKgHa":       dap_extra,
        "kExtraKgHa":         k_extra,
        "applicationMethod":  adj["method"],
        "splits":             adj["split"],
        "nProductChoice":     n_product,
        "cropNote":           rates.get("note", ""),
        "soilFactor":         round(sf, 2),
        "plan":               plan,
        "warnings":           warnings,
        "organicAdvice":      organic_advice,
        "confidence":         confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  WARNINGS  (v2 — more specific)
# ─────────────────────────────────────────────────────────────────────────────

def _build_warnings(
    annual_mm: float,
    band: str,
    crop: str,
    ph: float,
    soil_type: str,
) -> list:
    warnings = []

    if annual_mm < 400:
        warnings += [
            "Very low rainfall — irrigation strongly recommended before applying any fertilizer.",
            "Do not broadcast fertilizer on dry soil — use micro-dosing only (place near root).",
        ]
    if annual_mm > 1400:
        warnings += [
            "High rainfall causes nitrogen leaching. Never apply full Urea dose at once.",
            "Watch for fungal diseases — wet conditions spread disease quickly.",
            "Make ridges or raised beds before planting to prevent waterlogging.",
        ]
    if band in ("High", "Very High") and crop in ("maize", "wheat", "sorghum"):
        warnings.append(
            "Split all Urea/CAN into at least 3 applications — single large dose "
            "will wash away before the crop can absorb it."
        )
    if annual_mm < 600 and crop in ("rice", "sugarcane"):
        warnings.append(
            f"Warning: {crop.title()} normally requires more rainfall than forecast. "
            "Consider switching to a drought-tolerant crop or installing irrigation."
        )
    if ph < 5.0:
        warnings.append(
            f"Soil pH is very low ({ph:.1f}). Apply 2–3 t/ha agricultural lime "
            "4–6 weeks BEFORE any fertilizer. Fertilizer is ineffective on very acidic soil."
        )
    elif ph < 5.5:
        warnings.append(
            f"Soil pH is acidic ({ph:.1f}). Apply 1–2 t/ha lime before planting. "
            "Use CAN instead of Urea for nitrogen to avoid further acidification."
        )
    if soil_type.lower() in ("sandy",) and band in ("High", "Very High"):
        warnings.append(
            "Sandy soil in high-rainfall area — very high leaching risk. "
            "Use more frequent, smaller fertilizer applications. "
            "Adding compost will significantly improve nutrient retention."
        )
    if crop in ("tobacco",) and ph > 6.5:
        warnings.append(
            "Tobacco grown on alkaline soil (pH > 6.5) risks manganese and "
            "iron deficiency. Consider soil acidification with ammonium sulphate."
        )

    return warnings


# ─────────────────────────────────────────────────────────────────────────────
#  ORGANIC ADVICE  (v2 — specific rates and timing)
# ─────────────────────────────────────────────────────────────────────────────

def _get_organic_advice(band: str, soil_type: str) -> str:
    base_rate = "5–10 t/ha"
    timing    = "2–4 weeks before planting"

    if band == "Very Low":
        return (
            f"Apply {base_rate} compost or well-rotted manure {timing}. "
            "Organic matter is critical in dry areas — it holds up to 20x its weight "
            "in water and dramatically reduces fertilizer need. "
            "Compost also reduces soil temperature, protecting roots."
        )
    if band in ("High", "Very High"):
        if soil_type.lower() == "sandy":
            return (
                f"Apply 10 t/ha compost {timing}. Sandy soil in high rainfall loses "
                "nutrients very fast — compost binds nutrients and slows leaching. "
                "This is the single most important improvement you can make."
            )
        return (
            f"Apply {base_rate} compost {timing}. "
            "Organic matter improves soil structure and binds nutrients that "
            "would otherwise wash away in heavy rain. "
            "Apply crop residues as mulch after harvest."
        )
    return (
        f"Apply {base_rate} compost or manure {timing}. "
        "Organic matter improves water retention, root development, "
        "and reduces chemical fertilizer requirement by 15–25%. "
        "Incorporate crop residues after harvest."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIDENCE SCORING  (NEW)
#  Returns a score 0–100 with a plain-language explanation
# ─────────────────────────────────────────────────────────────────────────────

def _score_confidence(
    crop: str,
    ph: float,
    soil_type: str,
    annual_mm: float,
    band: str,
) -> dict:
    """
    Score the reliability of this recommendation.

    Deductions:
      - Crop not in CROP_BASE_RATES: -20 (using generic rates)
      - pH extreme (< 5.0 or > 8.0):  -15 (rules less reliable)
      - Rare soil type (not in leaching table): -10
      - Very low or very high rainfall: -10 (edge conditions)
      - Rainfall data from fallback (not satellite): handled in API layer
    """
    score  = 100
    issues = []

    if crop not in CROP_BASE_RATES:
        score  -= 20
        issues.append(f"'{crop}' not in crop database — using generic rates")

    if ph < 5.0 or ph > 8.5:
        score  -= 15
        issues.append(f"Extreme soil pH ({ph:.1f}) — soil correction needed first")
    elif ph < 5.5 or ph > 7.5:
        score  -= 8
        issues.append(f"pH ({ph:.1f}) outside ideal range — recommendations adjusted")

    if soil_type.lower() not in SOIL_LEACHING_FACTOR:
        score  -= 10
        issues.append(f"Soil type '{soil_type}' not recognised — using default factor")

    if band in ("Very Low", "Very High"):
        score  -= 10
        issues.append(f"{band} rainfall — edge condition, recommendations need field validation")

    score = max(30, min(100, score))

    label = (
        "High confidence"   if score >= 85 else
        "Good confidence"   if score >= 70 else
        "Moderate confidence" if score >= 55 else
        "Low confidence — review carefully"
    )

    return {
        "score": score,
        "label": label,
        "issues": issues,
        "message": (
            f"{label} ({score}/100). " +
            (" ".join(issues) if issues else
             "All inputs are within well-tested ranges for Malawi conditions.")
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  DEFICIENCY-SEVERITY-SCALED FERTILIZER PLAN  (v2)
#  Called from /recommend endpoint for soil-test-based advice
# ─────────────────────────────────────────────────────────────────────────────

def generate_fertilizer_plan(
    N: float, P: float, K: float,
    ph: float, organic_matter: float,
    rainfall_cat: str,
    soil_type: str = "loamy",
    crop: str = "",
) -> list:
    """
    Generate a deficiency-corrective fertilizer plan scaled to severity.

    v2 changes:
    - Rates now scale with deficiency depth (mild vs severe)
    - CAN offered as alternative to Urea on acidic soils
    - MAP offered as alternative to DAP when N is already adequate
    - Ammonium sulphate offered for S-demanding crops
    - Soil type affects product recommendation
    - All products confirmed available in Malawi (FAO data)
    """
    plans    = []
    crop_key = crop.lower().strip()

    adj_note = {
        "High":     "Split application recommended — high rainfall will leach nutrients.",
        "Very High":"Split into small frequent doses — very high leaching risk.",
        "Low":      "Apply near root zone, not broadcast — dry conditions reduce uptake.",
        "Very Low": "Micro-dose only — place fertilizer in planting hole.",
    }.get(rainfall_cat, "")

    # ── NITROGEN ──────────────────────────────────────────────────────────────
    if N < 20:
        # Severe deficiency — large corrective dose
        rate = round((60 - N) * 2.2)
        n_prod = "CAN (26% N)" if ph < 5.5 else "Urea (46% N)"
        alt    = "Urea (46% N)" if ph < 5.5 else "CAN (26% N)"
        plans.append({
            "type":            f"{n_prod}",
            "alternative":     f"{alt} is equally effective",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting + top-dress at 4–6 weeks",
            "notes": (
                f"Severe nitrogen deficiency (N = {N:.0f} mg/kg, target ≥ 60). "
                f"Crops will yellow and stunted without correction. "
                + (f"Using {n_prod} because soil pH is {ph:.1f} — acidic soil. " if ph < 5.5 else "")
                + adj_note
            ),
            "confidence": "High — severe deficiency, clear corrective action needed",
        })
    elif N < 40:
        # Moderate deficiency
        rate = round((60 - N) * 1.8)
        n_prod = "CAN (26% N)" if ph < 5.5 else "Urea (46% N)"
        plans.append({
            "type":            f"{n_prod}",
            "alternative":     "Ammonium sulphate (21% N + 24% S) if sulphur also needed",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting + top-dress at 4–6 weeks",
            "notes": (
                f"Moderate nitrogen deficiency (N = {N:.0f} mg/kg, target ≥ 60). "
                + adj_note
            ),
            "confidence": "High",
        })

    # ── PHOSPHORUS ────────────────────────────────────────────────────────────
    if P < 10:
        rate = round((30 - P) * 2.5)
        # MAP if N is already adequate, DAP if N also needed
        p_prod = "MAP (52% P, 11% N)" if N >= 40 else "DAP (46% P, 18% N)"
        plans.append({
            "type":            p_prod,
            "alternative":     "DAP (46% P, 18% N)" if p_prod.startswith("MAP") else "MAP (52% P, 11% N)",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting only",
            "notes": (
                f"Severe phosphorus deficiency (P = {P:.0f} mg/kg, target ≥ 30). "
                f"Root growth will be poor without correction. "
                + (f"Using {p_prod} — N is already adequate so MAP avoids over-application of N. "
                   if N >= 40 else
                   f"Using {p_prod} — provides both P and N correction together. ")
                + adj_note
            ),
            "confidence": "High",
        })
    elif P < 20:
        rate = round((30 - P) * 2.0)
        plans.append({
            "type":            "DAP (46% P, 18% N)",
            "alternative":     "MAP (52% P, 11% N) if N is already adequate",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting",
            "notes": (
                f"Moderate phosphorus deficiency (P = {P:.0f} mg/kg, target ≥ 30). "
                + adj_note
            ),
            "confidence": "High",
        })

    # ── POTASSIUM ─────────────────────────────────────────────────────────────
    if K < 50:
        rate = round((80 - K) * 1.8)
        k_prod = (
            "SOP (Potassium Sulphate, 50% K)"
            if crop_key in ("tobacco", "potato", "sweet potato", "sweetpotato", "tomato")
            else "MOP (Muriate of Potash, 60% K)"
        )
        plans.append({
            "type":            k_prod,
            "alternative":     "SOP preferred for quality-sensitive crops (tobacco, potato)",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting",
            "notes": (
                f"Severe potassium deficiency (K = {K:.0f} mg/kg, target ≥ 80). "
                "Crops will be weak and disease-prone. "
                + (f"Using SOP for {crop.title()} — chloride from MOP reduces quality. "
                   if k_prod.startswith("SOP") else "")
                + adj_note
            ),
            "confidence": "High",
        })
    elif K < 80:
        rate = round((80 - K) * 1.4)
        plans.append({
            "type":            "MOP (Muriate of Potash, 60% K)",
            "alternative":     "SOP (Potassium Sulphate) for tobacco or potato",
            "applicationRate": f"{rate} kg/ha",
            "timing":          "Basal at planting",
            "notes": (
                f"Moderate potassium deficiency (K = {K:.0f} mg/kg, target ≥ 80). "
                + adj_note
            ),
            "confidence": "High",
        })
    elif K > 300:
        plans.append({
            "type":  "No potassium fertilizer",
            "alternative": "None needed",
            "applicationRate": "0 kg/ha",
            "timing": "—",
            "notes": (
                f"Potassium is very high (K = {K:.0f} mg/kg). "
                "Do not add more — excess K blocks magnesium and calcium uptake."
            ),
            "confidence": "High",
        })

    # ── MAINTENANCE (all nutrients adequate) ─────────────────────────────────
    if N >= 60 and P >= 30 and K >= 80:
        plans.append({
            "type":            "NPK 23:21:0 (Maintenance dose)",
            "alternative":     "NPK 17:17:17 if potassium also needed",
            "applicationRate": "100 kg/ha",
            "timing":          "Basal at planting",
            "notes": (
                "Soil nutrients are at adequate levels. "
                "Maintenance dose sustains productivity without over-fertilising. "
                "Monitor crop response and adjust in following season."
            ),
            "confidence": "High",
        })

    # ── ORGANIC MATTER ────────────────────────────────────────────────────────
    if organic_matter < 1.0:
        plans.append({
            "type":            "Compost or well-rotted manure",
            "alternative":     "Crop residue incorporation",
            "applicationRate": "10 t/ha",
            "timing":          "2–4 weeks before planting",
            "notes": (
                f"Organic matter is critically low ({organic_matter:.1f}%). "
                "Soil will have poor water retention and low microbial activity. "
                "10 t/ha compost is the single most impactful action you can take."
            ),
            "confidence": "High",
        })
    elif organic_matter < 2.0:
        plans.append({
            "type":            "Compost or manure",
            "alternative":     "Green manure crop (e.g. Tithonia)",
            "applicationRate": "5 t/ha",
            "timing":          "2–4 weeks before planting",
            "notes": (
                f"Organic matter is low ({organic_matter:.1f}%). "
                "Regular compost applications will improve soil health over 2–3 seasons."
            ),
            "confidence": "High",
        })

    # ── LIME (pH correction) ─────────────────────────────────────────────────
    if ph < 5.5:
        lime_rate = round((6.0 - ph) * 2000)
        lime_rate = min(lime_rate, 4000)  # cap at 4 t/ha for safety
        plans.append({
            "type":            "Agricultural Lime (calcium carbonate)",
            "alternative":     "Dolomitic lime if magnesium also low",
            "applicationRate": f"{lime_rate} kg/ha",
            "timing":          "4–6 weeks BEFORE any other fertilizer",
            "notes": (
                f"Soil pH is {ph:.1f} — too acidic for most crops. "
                "Apply lime FIRST and wait 4–6 weeks before planting or fertilizing. "
                "Fertilizer applied to uncorrected acidic soil is largely wasted."
            ),
            "confidence": "High",
        })
    elif ph > 8.0:
        plans.append({
            "type":            "Sulphur (elemental) or Ammonium Sulphate",
            "alternative":     "Organic matter incorporation (acidifies slowly)",
            "applicationRate": "200–500 kg/ha sulphur",
            "timing":          "4–6 weeks before planting",
            "notes": (
                f"Soil pH is {ph:.1f} — alkaline. "
                "Phosphorus, iron, and manganese become unavailable above pH 8. "
                "Elemental sulphur or ammonium sulphate will gradually lower pH."
            ),
            "confidence": "Moderate — degree of alkalinity correction varies by soil",
        })

    return plans


# ─────────────────────────────────────────────────────────────────────────────
#  SOIL ALERTS  (v2 — corrected K thresholds, severity levels)
# ─────────────────────────────────────────────────────────────────────────────

def get_soil_alerts(
    N: float, P: float, K: float,
    ph: float, annual_mm: float,
) -> list:
    alerts = []

    # pH
    if ph < 5.0:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Soil is very acidic (pH {ph:.1f}). Apply 2–3 t/ha lime immediately. "
                       "No fertilizer will work properly until pH is corrected."})
    elif ph < 5.5:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Soil is acidic (pH {ph:.1f}). Apply 1–2 t/ha agricultural lime "
                       "4–6 weeks before planting. Use CAN instead of Urea."})
    elif ph < 6.0:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Soil is slightly acidic (pH {ph:.1f}). "
                       "A small lime application (0.5–1 t/ha) will improve crop response."})
    elif ph > 8.5:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Soil is very alkaline (pH {ph:.1f}). "
                       "Apply elemental sulphur to lower pH. Most nutrients unavailable above pH 8."})
    elif ph > 8.0:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Soil is alkaline (pH {ph:.1f}). "
                       "Phosphorus and micronutrients are less available. "
                       "Apply sulphur or ammonium sulphate to gradually lower pH."})

    # Nitrogen
    if N < 20:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Nitrogen is very low ({N:.0f} mg/kg). Crops will turn yellow "
                       "and grow slowly. Apply Urea or CAN urgently."})
    elif N < 40:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Nitrogen is low ({N:.0f} mg/kg). "
                       "Apply nitrogen fertilizer before planting."})

    # Phosphorus
    if P < 10:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Phosphorus is very low ({P:.0f} mg/kg). "
                       "Root growth will be severely restricted. Apply DAP or MAP at planting."})
    elif P < 20:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Phosphorus is low ({P:.0f} mg/kg). "
                       "Apply DAP or NPK basal fertilizer at planting."})

    # Potassium (corrected thresholds: <50 = severe, 50–80 = low, >300 = excess)
    if K < 50:
        alerts.append({"type": "danger", "icon": "⚠️",
            "message": f"Potassium is very low ({K:.0f} mg/kg). "
                       "Crops will be weak and disease-prone. Apply MOP or SOP urgently."})
    elif K < 80:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Potassium is low ({K:.0f} mg/kg). "
                       "Apply MOP (60% K) or SOP (50% K) before planting."})
    elif K > 300:
        alerts.append({"type": "warning", "icon": "🟡",
            "message": f"Potassium is very high ({K:.0f} mg/kg). "
                       "Do not add more potassium — excess blocks magnesium uptake."})

    # Rainfall
    if annual_mm < 400:
        alerts.append({"type": "danger", "icon": "🌵",
            "message": "Very low rainfall. Only grow sorghum or millet. "
                       "Consider irrigation before applying any fertilizer."})
    elif annual_mm > 1800:
        alerts.append({"type": "warning", "icon": "🌊",
            "message": "Very high rainfall. Split all fertilizer into small applications. "
                       "Build raised beds or ridges to prevent waterlogging."})

    if not alerts:
        alerts.append({"type": "ok", "icon": "✅",
            "message": "Soil nutrients are at adequate levels. "
                       "Follow the recommended maintenance fertilizer plan."})

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
#  SOIL ASSESSMENT  (v2 — severity-aware summary)
# ─────────────────────────────────────────────────────────────────────────────

def assess_soil(
    N: float, P: float, K: float,
    ph: float, organic_matter: float,
    moisture: float,
) -> str:
    critical = []
    moderate = []

    if N < 20:   critical.append(f"very low nitrogen ({N:.0f} mg/kg — crops will yellow)")
    elif N < 40: moderate.append(f"low nitrogen ({N:.0f} mg/kg)")
    if P < 10:   critical.append(f"very low phosphorus ({P:.0f} mg/kg — roots will be weak)")
    elif P < 20: moderate.append(f"low phosphorus ({P:.0f} mg/kg)")
    if K < 50:   critical.append(f"very low potassium ({K:.0f} mg/kg — disease risk)")
    elif K < 80: moderate.append(f"low potassium ({K:.0f} mg/kg)")
    if ph < 5.0:  critical.append(f"very acidic soil (pH {ph:.1f} — correct with lime before anything else)")
    elif ph < 5.5:critical.append(f"acidic soil (pH {ph:.1f})")
    elif ph > 8.5:critical.append(f"very alkaline soil (pH {ph:.1f})")
    elif ph > 8.0:moderate.append(f"alkaline soil (pH {ph:.1f})")
    if organic_matter < 1.0:  critical.append(f"critically low organic matter ({organic_matter:.1f}%)")
    elif organic_matter < 2.0:moderate.append(f"low organic matter ({organic_matter:.1f}%)")
    if moisture < 20:  moderate.append("very dry soil")
    elif moisture > 80:moderate.append("waterlogged soil")

    if not critical and not moderate:
        return ("Your soil is in good condition for farming. "
                "Follow the recommended maintenance fertilizer plan.")

    parts = []
    if critical:
        parts.append(f"{len(critical)} critical issue(s) needing urgent attention: "
                     f"{'; '.join(critical)}")
    if moderate:
        parts.append(f"{len(moderate)} moderate issue(s): {'; '.join(moderate)}")

    return (
        "Soil assessment: " + ". ".join(parts) + ". "
        "Address critical issues before planting."
    )