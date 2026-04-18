

from data.pest_disease_data import PEST_DISEASE_RISKS


def predict_pest_risks(
    crop_name:    str,
    rainfall_band: str,
    temperature:  float,
    humidity:     float,
) -> list[dict]:
    """
    Evaluate pest and disease risks for a given crop based on
    current weather and environmental conditions.

    Returns:
        List of risk dicts, each containing:
            name           — pest/disease name
            type           — "pest" or "disease"
            risk_level     — "Low Risk" / "Medium Risk" / "High Risk"
            risk_score     — integer 1–3 (1=low, 2=medium, 3=high)
            triggered_by   — what condition triggered the alert
            symptoms       — what to look for in the field
            action         — recommended control action
    """

    key   = crop_name.lower()
    risks = PEST_DISEASE_RISKS.get(key, [])

    results = []

    for entry in risks:

        triggered = False
        triggers  = []

        if rainfall_band in entry.get("trigger_rain", []):
            triggered = True
            triggers.append(f"{rainfall_band} rainfall")

        t_low, t_high = entry.get("trigger_temp", (0, 100))
        if t_low <= temperature <= t_high:
            triggered = True
            triggers.append(f"Temperature {temperature:.0f}°C (risk range {t_low}–{t_high}°C)")

        if humidity >= entry.get("trigger_humid", 101):
            triggered = True
            triggers.append(f"Humidity {humidity:.0f}% (threshold ≥{entry['trigger_humid']}%)")

     
        base_level = entry.get("risk_level", "medium")

        if triggered and base_level == "high":
            score = 3
            label = "High Risk"
        elif triggered and base_level == "medium":
            score = 2
            label = "Medium Risk"
        elif triggered and base_level == "low":
            score = 1
            label = "Low Risk"
        else:
           
            score = 1
            label = "Low Risk"

        results.append({
            "name":         entry["name"],
            "type":         entry["type"].capitalize(),
            "risk_level":   label,
            "risk_score":   score,
            "triggered_by": triggers if triggers else ["No triggering conditions detected"],
            "symptoms":     entry["symptoms"],
            "action":       entry["action"],
        })

    results.sort(key=lambda x: x["risk_score"], reverse=True)

    return results


def get_overall_risk_summary(pest_risks: list[dict]) -> dict:
    """
    Generate a one-line summary of the overall risk level for a crop.
    """

    if not pest_risks:
        return {
            "level":   "No Data",
            "icon":    "ℹ️",
            "message": "No pest/disease risk data available for this crop.",
        }

    high_count   = sum(1 for r in pest_risks if r["risk_score"] == 3)
    medium_count = sum(1 for r in pest_risks if r["risk_score"] == 2)

    if high_count >= 1:
        return {
            "level":   "High Risk",
            "icon":    "🔴",
            "message": (
                f"{high_count} HIGH risk pest/disease alert(s). "
                "Immediate field scouting recommended."
            ),
        }
    elif medium_count >= 1:
        return {
            "level":   "Medium Risk",
            "icon":    "🟡",
            "message": (
                f"{medium_count} MEDIUM risk alert(s). "
                "Monitor closely and prepare control measures."
            ),
        }
    else:
        return {
            "level":   "Low Risk",
            "icon":    "🟢",
            "message": "No significant pest/disease risk under current conditions.",
        }
