
import requests
import logging

logger = logging.getLogger(__name__)


def get_live_rainfall(lat: float, lon: float) -> dict | None:
    """
    Fetch 7-day precipitation forecast from Open-Meteo for a lat/lon.

    Returns:
        dict with keys:
            total_mm        — total rainfall over 7 days (mm)
            daily_forecast  — list of (date, mm) tuples
            source          — "Open-Meteo (Live)"
        or None if the request fails.
    """

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=precipitation_sum"
        "&timezone=Africa%2FBlantyre"
        "&forecast_days=7"
    )

    try:
        response = requests.get(url, timeout=8)
        response.raise_for_status()
        data = response.json()

        dates  = data["daily"]["time"]
        values = data["daily"]["precipitation_sum"]

       
        values = [v if v is not None else 0.0 for v in values]

        total = round(sum(values), 1)

        daily_forecast = [
            {"date": d, "mm": round(v, 1)}
            for d, v in zip(dates, values)
        ]

        return {
            "total_mm":       total,
            "daily_forecast": daily_forecast,
            "source":         "Open-Meteo (Live)",
        }

    except Exception as exc:
        logger.warning("Open-Meteo API failed: %s", exc)
        return None


def get_live_rainfall_mm(lat: float, lon: float) -> int | None:
    """
    Convenience function — returns total 7-day rainfall as a single integer,
    or None on failure.  Used as a drop-in replacement for the static forecast.
    """
    result = get_live_rainfall(lat, lon)
    if result:
        return int(result["total_mm"])
    return None
