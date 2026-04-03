
import datetime


def get_season_label() -> dict:
    """
    Returns season context based on today's date.

    Nov–May  → "This rain season"   (currently in rainy season)
    Jun–Oct  → "Next rain season"   (currently in dry season, predicting ahead)
    """
    today = datetime.date.today()
    month = today.month

    in_rainy_season = month >= 11 or month <= 5

    if in_rainy_season:
       
        if month >= 11:
            season_start_year = today.year
        else:
            season_start_year = today.year - 1

        season_end_year = season_start_year + 1
        label           = "This rain season"
        period          = f"Nov {season_start_year} – May {season_end_year}"
    else:
       
        season_start_year = today.year
        season_end_year   = today.year + 1
        label             = "Next rain season"
        period            = f"Nov {season_start_year} – May {season_end_year}"

    return {
        "label":              label,
        "period":             period,
        "in_rainy_season":    in_rainy_season,
        "season_start_year":  season_start_year,
        "season_end_year":    season_end_year,
        "current_month":      today.month,
        "current_year":       today.year,
    }


def get_weekly_summary(daily_data: list) -> list:
    """
    Group daily data into weeks.
    daily_data: [{date: "YYYY-MM-DD", mm: float}, ...]
    Returns: [{week: "Week 1", start: date, end: date, total_mm, avg_mm}, ...]
    """
    if not daily_data:
        return []

    weeks   = []
    chunk   = []
    week_n  = 1

    for i, day in enumerate(daily_data):
        chunk.append(day)
        if len(chunk) == 7 or i == len(daily_data) - 1:
            total = round(sum(d["mm"] for d in chunk), 1)
            avg   = round(total / len(chunk), 2)
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


def estimate_season_total(monthly_distribution: list, annual_forecast: float) -> dict:
    """
    Estimate rainfall specifically for the Nov–May rainy season
    based on the annual forecast and monthly distribution percentages.
    """
   
    rainy_months = {
        "Nov": 0.08, "Dec": 0.14, "Jan": 0.20,
        "Feb": 0.22, "Mar": 0.18, "Apr": 0.09, "May": 0.04,
    }
    dry_months = {
        "Jun": 0.01, "Jul": 0.01, "Aug": 0.00,
        "Sep": 0.01, "Oct": 0.02,
    }

    
    month_totals = {item["month"]: item["mm"] for item in monthly_distribution} \
        if monthly_distribution else {}

    season_mm = 0.0
    for month, pct in rainy_months.items():
        if month in month_totals:
            season_mm += month_totals[month]
        else:
            season_mm += annual_forecast * pct

    return {
        "season_total_mm":  round(season_mm, 1),
        "season_months":    list(rainy_months.keys()),
        "dry_season_months": list(dry_months.keys()),
    }