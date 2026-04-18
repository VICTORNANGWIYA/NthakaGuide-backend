
from data.crop_yield_data import CROP_YIELD_DATA



_BAND_ORDER = {
    "Very Low": 0,
    "Low":      1,
    "Moderate": 2,
    "High":     3,
    "Very High":4,
}


N_OPTIMAL  = 50   
P_OPTIMAL  = 25    
K_OPTIMAL  = 200  
OM_OPTIMAL = 3.0   


def predict_yield(
    crop_name:    str,
    nitrogen:     float,
    phosphorus:   float,
    potassium:    float,
    ph:           float,
    organic_matter: float,
    rainfall_band:  str,
) -> dict:
    """
    Predict expected crop yield for given soil and climate conditions.

    Returns a dict with:
        predicted_tha      — predicted yield (tons/ha)
        base_tha           — average smallholder yield
        potential_tha      — achievable yield under good management
        yield_gap_tha      — difference between predicted and potential
        yield_category     — "Poor" / "Fair" / "Good" / "Excellent"
        limiting_factors   — list of factors reducing yield
        improvement_tips   — list of actionable recommendations
        unit               — unit string (e.g. "tons/ha")
    """

    key  = crop_name.lower()
    data = CROP_YIELD_DATA.get(key)

    if data is None:
        
        data = {
            "base_yield_tha":   1.5,
            "potential_tha":    3.5,
            "min_tha":          0.5,
            "n_response":       0.03,
            "rain_sensitivity": {"Very Low":-0.20,"Low":-0.10,"Moderate":0.00,"High":0.10,"Very High":0.05},
            "soil_ph_optimal":  (5.5, 7.0),
            "unit":             "tons/ha",
            "notes":            "",
        }

    base      = data["base_yield_tha"]
    potential = data["potential_tha"]
    minimum   = data["min_tha"]
    n_resp    = data["n_response"]
    rain_adj  = data["rain_sensitivity"].get(rainfall_band, 0.0)
    ph_low, ph_high = data["soil_ph_optimal"]

    predicted = base

    limiting_factors   = []
    improvement_tips   = []

    n_factor = (nitrogen - N_OPTIMAL) * n_resp
    if nitrogen < N_OPTIMAL * 0.6:
        limiting_factors.append(f"Low soil nitrogen ({nitrogen:.0f} mg/kg) — target >50 mg/kg")
        improvement_tips.append("Apply recommended basal nitrogen fertilizer at planting")
    elif nitrogen > N_OPTIMAL * 1.8:
        n_factor = -0.05 * base        
        limiting_factors.append(f"Excess nitrogen ({nitrogen:.0f} mg/kg) may reduce grain quality")
        improvement_tips.append("Reduce nitrogen application to avoid lodging and quality loss")
    predicted += n_factor

    if phosphorus < P_OPTIMAL * 0.5:
        p_penalty = -0.12 * base
        predicted += p_penalty
        limiting_factors.append(f"Very low phosphorus ({phosphorus:.0f} mg/kg) limits root growth")
        improvement_tips.append("Apply DAP or SSP basal fertilizer to correct phosphorus deficiency")
    elif phosphorus < P_OPTIMAL:
        p_penalty = -0.06 * base
        predicted += p_penalty
        limiting_factors.append(f"Low phosphorus ({phosphorus:.0f} mg/kg)")
        improvement_tips.append("Apply phosphorus-containing fertilizer at planting")

  
    if potassium < K_OPTIMAL * 0.5:
        k_penalty = -0.08 * base
        predicted += k_penalty
        limiting_factors.append(f"Low potassium ({potassium:.0f} mg/kg) affects disease resistance")
        improvement_tips.append("Apply potassium-containing fertilizer or wood ash (K-source)")

    if ph < ph_low:
        ph_penalty = min(0.5, (ph_low - ph) * 0.15) * base
        predicted -= ph_penalty
        limiting_factors.append(f"Acidic soil (pH {ph:.1f}) limits nutrient availability")
        improvement_tips.append(f"Apply agricultural lime to raise pH to {ph_low}–{ph_high}")
    elif ph > ph_high:
        ph_penalty = min(0.3, (ph - ph_high) * 0.10) * base
        predicted -= ph_penalty
        limiting_factors.append(f"Alkaline soil (pH {ph:.1f}) may cause micronutrient deficiency")
        improvement_tips.append("Apply sulphur or acidifying fertilizers to lower pH")

    if organic_matter < 1.5:
        om_penalty = -0.10 * base
        predicted += om_penalty
        limiting_factors.append(f"Very low organic matter ({organic_matter:.1f}%) — poor water retention")
        improvement_tips.append("Incorporate crop residues and apply compost or farmyard manure")
    elif organic_matter >= OM_OPTIMAL:
        om_bonus = 0.05 * base
        predicted += om_bonus

    
    predicted += rain_adj * base
    if rainfall_band in ("Very Low", "Low"):
        limiting_factors.append(f"Low rainfall ({rainfall_band}) is the primary yield constraint")
        improvement_tips.append("Use drought-tolerant varieties and plant at start of rains")
    elif rainfall_band == "Very High":
        limiting_factors.append("Very high rainfall risk: waterlogging may reduce yield")
        improvement_tips.append("Ensure good drainage ridges and split nitrogen application")

    predicted = max(minimum, min(potential, round(predicted, 2)))


    ratio = predicted / potential
    if ratio >= 0.75:
        category = "Excellent"
    elif ratio >= 0.50:
        category = "Good"
    elif ratio >= 0.30:
        category = "Fair"
    else:
        category = "Poor"

    yield_gap = round(potential - predicted, 2)

    if not limiting_factors:
        limiting_factors.append("No major limiting factors detected under current conditions")

    if not improvement_tips:
        improvement_tips.append("Maintain current soil management practices")

    return {
        "predicted_tha":     predicted,
        "base_tha":          base,
        "potential_tha":     potential,
        "minimum_tha":       minimum,
        "yield_gap_tha":     yield_gap,
        "yield_category":    category,
        "limiting_factors":  limiting_factors,
        "improvement_tips":  improvement_tips,
        "unit":              data.get("unit", "tons/ha"),
        "notes":             data.get("notes", ""),
    }
