
LEGUMES = {
    "beans", "groundnuts", "soybean", "pigeonpeas", "cowpea",
    "mungbean", "blackgram", "chickpea", "kidneybeans", "lentil",
}

HEAVY_FEEDERS = {
    "maize", "tobacco", "cotton", "sugarcane", "rice",
}

GOOD_ROTATIONS = {
    "maize":      ["beans", "groundnuts", "soybean", "pigeonpeas", "cowpea"],
    "tobacco":    ["maize", "beans", "groundnuts"],
    "cotton":     ["maize", "beans", "soybean"],
    "rice":       ["pigeonpeas", "beans", "groundnuts"],
    "cassava":    ["maize", "groundnuts", "beans"],
    "sorghum":    ["beans", "groundnuts", "cowpea"],
    "millet":     ["beans", "groundnuts", "soybean"],
    "beans":      ["maize", "sorghum", "cassava"],
    "groundnuts": ["maize", "sorghum", "cassava"],
    "soybean":    ["maize", "sorghum"],
    "sweetpotato":   ["maize", "beans"],
    "sunflower":     ["maize", "beans"],
}


def get_rotation_advice(previous_crop: str, current_crop: str):
    prev = (previous_crop or "").strip().lower()
    curr = current_crop.strip().lower()

    if not prev or prev in ("none", "unknown", ""):
        return None

    # Same crop warning
    if prev == curr:
        extra = ""
        if curr in HEAVY_FEEDERS:
            extra = (
                f" {curr.title()} is a heavy feeder — "
                "repeating it depletes soil nitrogen and increases disease pressure."
            )
        return {
            "type": "warning",
            "message": f"You grew {curr.title()} last season and are repeating it.{extra}",
            "recommendation": (
                "Consider rotating with a legume such as beans, groundnuts, or soybean "
                "to restore soil nitrogen and break pest cycles. "
                "If you must repeat, increase fertilizer rates and scout for pests early."
            ),
        }

    if curr in LEGUMES and prev not in LEGUMES:
        return {
            "type": "positive",
            "message": f"Excellent rotation — growing {curr.title()} after {prev.title()}.",
            "recommendation": (
                f"{curr.title()} will fix atmospheric nitrogen into the soil, "
                "reducing your fertilizer needs for the next season. "
                "Leave crop residues to decompose and further enrich the soil."
            ),
        }

    good_after_prev = GOOD_ROTATIONS.get(prev, [])
    if curr in good_after_prev:
        return {
            "type": "positive",
            "message": f"Good rotation — {curr.title()} after {prev.title()}.",
            "recommendation": (
                "This rotation helps break pest and disease cycles "
                "and maintains soil health. Apply recommended fertilizer as usual."
            ),
        }

    if prev in LEGUMES and curr not in LEGUMES:
        return {
            "type": "positive",
            "message": (
                f"Good sequence — {prev.title()} last season enriched the soil "
                f"with nitrogen, benefiting {curr.title()} this season."
            ),
            "recommendation": (
                "You may be able to reduce your nitrogen fertilizer rate slightly. "
                "Monitor crop colour and adjust top-dressing if needed."
            ),
        }

    return {
        "type": "info",
        "message": f"{curr.title()} can follow {prev.title()} without major concerns.",
        "recommendation": (
            "Ensure proper soil preparation, recommended fertilizer rates, "
            "and early pest scouting for best results."
        ),
    }


def get_general_rotation_tip(previous_crop: str):
    prev = (previous_crop or "").strip().lower()
    if not prev or prev in ("none", "unknown"):
        return None

    suggestions = GOOD_ROTATIONS.get(prev)
    if suggestions:
        names = ", ".join(c.title() for c in suggestions[:3])
        return f"After {prev.title()}, consider: {names} for best soil health."

    if prev in LEGUMES:
        return f"After {prev.title()} (a legume), most cereals and cash crops will benefit from the soil nitrogen."

    return None