
import requests
import logging
import datetime
import calendar

logger = logging.getLogger(__name__)

NASA_BASE = "https://power.larc.nasa.gov/api/temporal"

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]



def _today() -> datetime.date:
    return datetime.date.today()

def _current_year() -> int:
    return _today().year

def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

def _ewma_forecast(values: list, alpha: float = 0.3) -> float:
    """EWMA on annual values list → next-year forecast."""
    if not values:
        return 900.0
    ewma = float(values[0])
    for v in values[1:]:
        ewma = alpha * float(v) + (1 - alpha) * ewma
   
    if len(values) >= 3:
        ewma_old = float(values[-3])
        for v in values[-2:]:
            ewma_old = alpha * float(v) + (1 - alpha) * ewma_old
        trend = ewma - ewma_old
        return max(200.0, round(ewma + trend * 0.5, 1))
    return max(200.0, round(ewma, 1))




def get_satellite_annual_history(lat: float, lon: float) -> dict | None:
    """
    Fetch annual rainfall totals from NASA POWER for 2000 → last full year.

    NASA POWER annual endpoint returns PRECTOTCORR as mm/day annual average.
    Multiply by 365 (or 366 for leap years) to get total mm/year.

    Returns:
        {
          years:     [2000, 2001, ..., 2024],
          values:    [850.2, 920.1, ...],   # mm/year
          annual_mm: 895.3,                 # EWMA forecast for next season
          source:    "NASA POWER Satellite (2000–2024)",
        }
    """
    end_year   = _current_year() - 1
    start_year = 2000

    url = (
        f"{NASA_BASE}/annual/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_year}&end={end_year}"
        f"&format=JSON"
    )

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        raw         = resp.json()
        annual_data = raw["properties"]["parameter"]["PRECTOTCORR"]

        years  = []
        values = []

        for key in sorted(annual_data.keys()):
            
            try:
                y = int(key)
            except ValueError:
                continue

            val_per_day = annual_data[key]
           
            if val_per_day is None or val_per_day < 0:
                continue

            days   = 366 if calendar.isleap(y) else 365
            annual = round(val_per_day * days, 1)
            years.append(y)
            values.append(annual)

        if not years:
            logger.warning("NASA annual history: no valid data rows")
            return None

        forecast = _ewma_forecast(values)

        return {
            "years":     years,
            "values":    values,
            "annual_mm": forecast,
            "source":    f"NASA POWER Satellite (2000–{years[-1]})",
        }

    except Exception as exc:
        logger.warning("NASA annual history failed: %s", exc)
        return None



def get_satellite_monthly(lat: float, lon: float, year: int = None) -> dict | None:
    """
    Fetch monthly rainfall totals for a given year (default = current year).
    Only fetches up to the last completed month to avoid partial data.

    Returns:
        {
          monthly: [
            {"month": "Jan", "year": 2025, "mm": 120.5},
            ...
          ]
        }
    """
    today = _today()
    if year is None:
        year = today.year

    if year == today.year:
        end_month = today.month - 1
        if end_month < 1:
            year      -= 1
            end_month  = 12
    else:
        end_month = 12

    start_str = f"{year}0101"
    end_str   = f"{year}{end_month:02d}{_days_in_month(year, end_month):02d}"

    url = (
        f"{NASA_BASE}/monthly/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_str}&end={end_str}"
        f"&format=JSON"
    )

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        raw     = resp.json()
        monthly = raw["properties"]["parameter"]["PRECTOTCORR"]

        results = []
        for key in sorted(monthly.keys()):
          
            if len(key) != 6:
                continue
            try:
                y = int(key[:4])
                m = int(key[4:6])
            except ValueError:
                continue

            val = monthly[key]
            if val is None or val < 0:
                continue

            days   = _days_in_month(y, m)
            mm_val = round(val * days, 1)
            results.append({
                "month": MONTH_NAMES[m - 1],
                "year":  y,
                "mm":    mm_val,
            })

        return {"monthly": results} if results else None

    except Exception as exc:
        logger.warning("NASA monthly failed: %s", exc)
        return None


def get_satellite_daily(lat: float, lon: float, days: int = 30) -> dict | None:
    """
    Fetch daily rainfall for the last `days` days from NASA POWER.
    NASA POWER daily data has a ~3–5 day lag so we fetch up to yesterday.

    Returns:
        {
          daily:      [{"date": "2025-03-01", "mm": 12.3}, ...],
          total_mm:   145.6,
          avg_mm:     4.85,
        }
    """
    today     = _today()
    end_date  = today - datetime.timedelta(days=1)  
    start_date = end_date - datetime.timedelta(days=days - 1)

    start_str = start_date.strftime("%Y%m%d")
    end_str   = end_date.strftime("%Y%m%d")

    url = (
        f"{NASA_BASE}/daily/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_str}&end={end_str}"
        f"&format=JSON"
    )

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        raw   = resp.json()
        daily = raw["properties"]["parameter"]["PRECTOTCORR"]

        results = []
        for date_str in sorted(daily.keys()):
            val = daily[date_str]
            if val is None or val < 0:
                continue
            results.append({
                "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                "mm":   round(float(val), 2),  
            })

        if not results:
            return None

        total = round(sum(r["mm"] for r in results), 1)
        avg   = round(total / len(results), 2)

        return {
            "daily":    results,
            "total_mm": total,
            "avg_mm":   avg,
        }

    except Exception as exc:
        logger.warning("NASA daily failed: %s", exc)
        return None


def get_satellite_annual_mm(lat: float, lon: float) -> float | None:
    """
    Returns only the EWMA annual forecast mm.
    Used by recommend route — backward compatible with old interface.
    """
    hist = get_satellite_annual_history(lat, lon)
    return hist["annual_mm"] if hist else None


def get_satellite_rainfall(lat: float, lon: float) -> dict | None:
    """
    Legacy interface used by old rainfall route.
    Returns { annual_mm, monthly_mm } — backward compatible.
    """
    hist    = get_satellite_annual_history(lat, lon)
    monthly = get_satellite_monthly(lat, lon)

    if not hist:
        return None

    return {
        "annual_mm":  hist["annual_mm"],
        "monthly_mm": monthly["monthly"] if monthly else [],
        "source":     hist["source"],
    }