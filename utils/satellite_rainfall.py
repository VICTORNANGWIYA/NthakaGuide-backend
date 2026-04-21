"""
utils/satellite_rainfall.py

Performance fix: replaced 26 sequential NASA calls with ONE call
covering 2000–present. Cache holds data for the entire rainy season
(expires at end of April or end of October — whichever is next).
"""

import requests
import logging
import datetime
import calendar
from typing import Optional

logger = logging.getLogger(__name__)

NASA_BASE    = "https://power.larc.nasa.gov/api/temporal"
HISTORY_FROM = 2000
TIMEOUT      = 60  

MONTH_NAMES = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]




def _seconds_until_season_end() -> int:
    """
    Returns seconds until the end of the current agricultural season.
    
    Malawi seasons:
      Rainy season  → Nov 1  to Apr 30  (cache until May 1)
      Dry season    → May 1  to Oct 31  (cache until Nov 1)
    
    This means historical NASA data fetched in January stays cached
    until May 1 — no unnecessary re-fetching during the same season.
    """
    today = datetime.date.today()
    year  = today.year

    if today.month >= 11:
       
        end = datetime.date(year + 1, 5, 1)
    elif today.month <= 4:
      
        end = datetime.date(year, 5, 1)
    else:
        
        end = datetime.date(year, 11, 1)

    delta = datetime.datetime.combine(end, datetime.time.min) - \
            datetime.datetime.now()
    
    
    return max(3600, int(delta.total_seconds()))


SEASON_CACHE_TIMEOUT = _seconds_until_season_end()




def _today() -> datetime.date:
    return datetime.date.today()

def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]

def _last_complete_year() -> int:
    today = _today()
    if today.month < 4:
        return today.year - 2
    return today.year - 1


def _fetch_all_years_daily(lat: float, lon: float) -> Optional[dict]:
    """
    ONE NASA request covering HISTORY_FROM to last complete year.
    Returns { "YYYYMMDD": mm, ... } for all days across all years.
    Much faster than 26 individual requests.
    """
    end_year  = _last_complete_year()
    start_str = f"{HISTORY_FROM}0101"
    end_str   = f"{end_year}1231"

    url = (
        f"{NASA_BASE}/daily/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_str}&end={end_str}"
        f"&format=JSON"
    )

    logger.info(
        "NASA single fetch: %d–%d for lat=%.4f lon=%.4f",
        HISTORY_FROM, end_year, lat, lon,
    )

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        raw = resp.json()
        return raw["properties"]["parameter"]["PRECTOTCORR"]
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        logger.warning(
            "NASA single fetch HTTP %s lat=%.4f lon=%.4f", status, lat, lon
        )
    except Exception as exc:
        logger.warning(
            "NASA single fetch error lat=%.4f lon=%.4f: %s", lat, lon, exc
        )
    return None


def _group_by_year(daily: dict) -> dict:
    """
    Takes the flat { "YYYYMMDD": mm } dict and groups into:
    { 2000: [mm, mm, ...], 2001: [...], ... }
    """
    by_year: dict[int, list] = {}
    for date_str, val in daily.items():
        if len(date_str) != 8 or val is None or float(val) < 0:
            continue
        year = int(date_str[:4])
        by_year.setdefault(year, []).append(float(val))
    return by_year


def _sum_year(values: list, year: int) -> Optional[float]:
    if len(values) < 300:
        logger.warning(
            "Year %d has only %d valid days — skipping", year, len(values)
        )
        return None
    return round(sum(values), 1)


def _ewma_forecast(values: list, alpha: float = 0.3) -> float:
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




def get_satellite_annual_history(lat: float, lon: float) -> Optional[dict]:
    """
    Fetches ALL years in ONE NASA request, groups by year, sums to annual
    totals, then runs EWMA to forecast the coming season.

    Result is cached for the entire agricultural season (see SEASON_CACHE_TIMEOUT).
    """
    daily = _fetch_all_years_daily(lat, lon)
    if daily is None:
        return None

    by_year = _group_by_year(daily)

    years  = []
    values = []

    for year in sorted(by_year.keys()):
        total = _sum_year(by_year[year], year)
        if total is not None:
            years.append(year)
            values.append(total)

    if not years:
        logger.warning(
            "No valid annual totals for lat=%.4f lon=%.4f", lat, lon
        )
        return None

    forecast = _ewma_forecast(values)

    logger.info(
        "Annual history ready: %d years, forecast=%.1fmm, "
        "cache expires in %d hours",
        len(years), forecast, SEASON_CACHE_TIMEOUT // 3600,
    )

    return {
        "years":     years,
        "values":    values,
        "annual_mm": forecast,
        "source":    f"NASA POWER Daily ({years[0]}–{years[-1]})",
    }


def get_satellite_monthly(
    lat: float, lon: float, year: int = None
) -> Optional[dict]:
    today = _today()
    if year is None:
        year = today.year

    if year == today.year:
        last_month = today.month - 1
        if last_month < 1:
            year      -= 1
            last_month = 12
    else:
        last_month = 12

    start_str = f"{year}0101"
    end_str   = f"{year}{last_month:02d}{_days_in_month(year, last_month):02d}"

    url = (
        f"{NASA_BASE}/daily/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_str}&end={end_str}"
        f"&format=JSON"
    )

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        raw   = resp.json()
        daily = raw["properties"]["parameter"]["PRECTOTCORR"]
    except Exception as exc:
        logger.warning("NASA monthly-via-daily error: %s", exc)
        return None

    monthly_totals: dict[int, float] = {}
    for date_str, val in daily.items():
        if len(date_str) != 8 or val is None or float(val) < 0:
            continue
        m = int(date_str[4:6])
        monthly_totals[m] = monthly_totals.get(m, 0.0) + float(val)

    if not monthly_totals:
        return None

    return {
        "monthly": [
            {"month": MONTH_NAMES[m - 1], "year": year, "mm": round(monthly_totals[m], 1)}
            for m in sorted(monthly_totals.keys())
        ]
    }


def get_satellite_daily(
    lat: float, lon: float, days: int = 30
) -> Optional[dict]:
    today      = _today()
    end_date   = today - datetime.timedelta(days=5)
    start_date = end_date - datetime.timedelta(days=days - 1)

    url = (
        f"{NASA_BASE}/daily/point"
        f"?parameters=PRECTOTCORR"
        f"&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_date.strftime('%Y%m%d')}&end={end_date.strftime('%Y%m%d')}"
        f"&format=JSON"
    )

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        daily = resp.json()["properties"]["parameter"]["PRECTOTCORR"]
    except Exception as exc:
        logger.warning("NASA daily failed: %s", exc)
        return None

    results = [
        {
            "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
            "mm":   round(float(v), 2),
        }
        for d, v in sorted(daily.items())
        if v is not None and float(v) >= 0
    ]

    if not results:
        return None

    total = round(sum(r["mm"] for r in results), 1)
    return {
        "daily":    results,
        "total_mm": total,
        "avg_mm":   round(total / len(results), 2),
    }


def get_satellite_annual_mm(lat: float, lon: float) -> Optional[float]:
    hist = get_satellite_annual_history(lat, lon)
    return hist["annual_mm"] if hist else None


def get_satellite_rainfall(lat: float, lon: float) -> Optional[dict]:
    hist    = get_satellite_annual_history(lat, lon)
    monthly = get_satellite_monthly(lat, lon)
    if not hist:
        return None
    return {
        "annual_mm":  hist["annual_mm"],
        "monthly_mm": monthly["monthly"] if monthly else [],
        "source":     hist["source"],
    }