"""
utils/season_helper.py
Malawi seasonal context helpers — rainy season is Nov–May.
"""

import logging
import datetime

logger = logging.getLogger("NthakaGuide.season_helper")

# 3-letter abbreviations used as month keys throughout the system.
# Must match the keys produced by get_monthly_distribution() in algorithms.py
# AND by the NASA POWER normalisation in satellite_rainfall.py.
_MONTH_ABBR = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# Malawi seasonal percentages (fraction of annual rainfall per month).
# Must stay in sync with PERCENTAGES in algorithms.get_monthly_distribution().
_RAINY_MONTH_PCT: dict[str, float] = {
    "Nov": 0.08, "Dec": 0.14, "Jan": 0.20,
    "Feb": 0.22, "Mar": 0.18, "Apr": 0.09, "May": 0.04,
}
_DRY_MONTH_PCT: dict[str, float] = {
    "Jun": 0.01, "Jul": 0.01, "Aug": 0.00,
    "Sep": 0.01, "Oct": 0.02,
}


# ═══════════════════════════════════════════════════════════════════════════
#  SEASON LABEL
# ═══════════════════════════════════════════════════════════════════════════

def get_season_label() -> dict:
    """
    Return season context based on today's date.

    Nov–May → "This rain season"   (currently in the rainy season)
    Jun–Oct → "Next rain season"   (dry season — predicting the next season)

    All year-boundary logic is verified for every month:
      Jan 2026 → Nov 2025 – May 2026  (rainy, season started last year)
      May 2026 → Nov 2025 – May 2026  (rainy, season ends this month)
      Jun 2026 → Nov 2026 – May 2027  (dry, next season starts later this year)
      Oct 2026 → Nov 2026 – May 2027  (dry)
      Nov 2026 → Nov 2026 – May 2027  (rainy, season just started)
      Dec 2026 → Nov 2026 – May 2027  (rainy)
    """
    today = datetime.date.today()
    month = today.month

    in_rainy_season: bool = (month >= 11 or month <= 5)

    if in_rainy_season:
        # Current rainy season started in November of:
        #   - this year  (if we are in Nov or Dec)
        #   - last year  (if we are in Jan–May)
        season_start_year = today.year if month >= 11 else today.year - 1
        label             = "This rain season"
    else:
        # Next rainy season starts in November of this year
        season_start_year = today.year
        label             = "Next rain season"

    season_end_year = season_start_year + 1
    period          = f"Nov {season_start_year} – May {season_end_year}"

    return {
        "label":             label,
        "period":            period,
        "in_rainy_season":   in_rainy_season,
        "season_start_year": season_start_year,
        "season_end_year":   season_end_year,
        "current_month":     today.month,
        "current_year":      today.year,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  WEEKLY SUMMARY
# ═══════════════════════════════════════════════════════════════════════════

def get_weekly_summary(daily_data: list) -> list:
    """
    Group daily data into consecutive 7-day chunks (not calendar weeks).

    Chunking starts from the first record in daily_data regardless of the
    day-of-week — this is intentional for rolling 30-day satellite windows.

    Args:
        daily_data: list of {"date": "YYYY-MM-DD", "mm": float}

    Returns:
        list of:
        {
            "week":     "Week 1",
            "start":    "YYYY-MM-DD",
            "end":      "YYYY-MM-DD",
            "days":     int,        # 1–7 (last chunk may be shorter)
            "total_mm": float,
            "avg_mm":   float,
        }
    """
    if not daily_data:
        return []

    weeks  = []
    chunk  = []
    week_n = 1

    for i, day in enumerate(daily_data):
        chunk.append(day)
        if len(chunk) == 7 or i == len(daily_data) - 1:
            total = round(sum(d["mm"] for d in chunk), 1)
            avg   = round(total / len(chunk), 2) if chunk else 0.0
            weeks.append({
                "week":     f"Week {week_n}",
                "start":    chunk[0]["date"],
                "end":      chunk[-1]["date"],
                "days":     len(chunk),
                "total_mm": total,
                "avg_mm":   avg,
            })
            chunk  = []
            week_n += 1

    return weeks


# ═══════════════════════════════════════════════════════════════════════════
#  SEASON TOTAL ESTIMATE
# ═══════════════════════════════════════════════════════════════════════════

def estimate_season_total(monthly_distribution: list, annual_forecast: float) -> dict:
    """
    Estimate rainfall for the Nov–May rainy season.

    Uses monthly_distribution values where available; falls back to
    annual_forecast × monthly percentage for any missing month.

    FIX: month_totals lookup now normalises keys to 3-letter abbreviations
    before matching against _RAINY_MONTH_PCT, so full month names
    ("November"), numeric keys (11), or 3-letter keys ("Nov") all work.
    Missing months are logged so silent fallbacks are visible.

    Args:
        monthly_distribution: list of {"month": str, "mm": float}
            month key may be "Nov", "November", or "11" — all accepted.
        annual_forecast: float — annual rainfall (mm) used as fallback.

    Returns:
        {
            "season_total_mm":   float,
            "season_months":     list[str],   # always ["Nov","Dec",...]
            "dry_season_months": list[str],
            "months_from_data":  list[str],   # which months used real data
            "months_from_pct":   list[str],   # which months used fallback %
        }
    """
    # Build a lookup keyed by normalised 3-letter abbreviation
    month_totals: dict[str, float] = {}

    if monthly_distribution:
        for item in monthly_distribution:
            raw_key = str(item.get("month", "")).strip()
            abbr    = _normalise_month_key(raw_key)
            if abbr:
                month_totals[abbr] = float(item.get("mm", 0.0))
            else:
                logger.warning(
                    "estimate_season_total: unrecognised month key %r — skipping",
                    raw_key,
                )

    season_mm      = 0.0
    from_data: list[str] = []
    from_pct:  list[str] = []

    for month_abbr, pct in _RAINY_MONTH_PCT.items():
        if month_abbr in month_totals:
            season_mm += month_totals[month_abbr]
            from_data.append(month_abbr)
        else:
            fallback = annual_forecast * pct
            season_mm += fallback
            from_pct.append(month_abbr)
            logger.debug(
                "estimate_season_total: %s not in data — using %.1fmm (%.0f%% of %.0fmm annual)",
                month_abbr, fallback, pct * 100, annual_forecast,
            )

    return {
        "season_total_mm":   round(season_mm, 1),
        "season_months":     list(_RAINY_MONTH_PCT.keys()),
        "dry_season_months": list(_DRY_MONTH_PCT.keys()),
        "months_from_data":  from_data,   # transparency — which months had real data
        "months_from_pct":   from_pct,    # transparency — which used fallback %
    }


# ═══════════════════════════════════════════════════════════════════════════
#  INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

# Map accepted month representations → 3-letter abbreviation
_FULL_TO_ABBR: dict[str, str] = {
    "january": "Jan",   "february": "Feb",  "march": "Mar",
    "april":   "Apr",   "may":      "May",  "june":  "Jun",
    "july":    "Jul",   "august":   "Aug",  "september": "Sep",
    "october": "Oct",   "november": "Nov",  "december":  "Dec",
}
_NUM_TO_ABBR: dict[str, str] = {
    str(i + 1): abbr for i, abbr in enumerate(_MONTH_ABBR)
}
_ABBR_SET = set(_MONTH_ABBR)


def _normalise_month_key(raw: str) -> str | None:
    """
    Convert any month representation to a 3-letter abbreviation.

    Accepts:
        "Nov", "nov"               → "Nov"
        "November", "november"     → "Nov"
        "11", "1"                  → "Nov", "Jan"

    Returns None if the key cannot be recognised.
    """
    stripped = raw.strip()

    # Already a 3-letter abbreviation (case-insensitive)
    title = stripped.title()
    if title in _ABBR_SET:
        return title

    # Full month name
    lower = stripped.lower()
    if lower in _FULL_TO_ABBR:
        return _FULL_TO_ABBR[lower]

    # Numeric string "1"–"12"
    if stripped.isdigit() and stripped in _NUM_TO_ABBR:
        return _NUM_TO_ABBR[stripped]

    return None