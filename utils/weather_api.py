"""
utils/weather_api.py
Live 7-day rainfall forecast from Open-Meteo (free, no API key required).
Used for display only — never fed to the ML model (annual figure is used there).
"""

import time
import logging
import requests

logger = logging.getLogger("NthakaGuide.weather_api")

_OPEN_METEO_URL  = "https://api.open-meteo.com/v1/forecast"
_FORECAST_DAYS   = 7
_TIMEOUT_SECONDS = 8
_MAX_RETRIES     = 1        # one retry on transient 5xx errors
_RETRY_DELAY_S   = 1.0      # seconds between retry attempts


def get_live_rainfall(lat: float, lon: float) -> dict | None:
    """
    Fetch a 7-day precipitation forecast from Open-Meteo for a lat/lon.

    Returns a dict with:
        total_mm        — total rainfall over 7 days (mm)
        daily_forecast  — list of {"date": "YYYY-MM-DD", "mm": float}
        source          — "Open-Meteo (Live)"

    Returns None if the request fails after retries.

    FIX 1: Uses params dict instead of a fragile multi-line f-string URL,
            making it safe to add or change parameters.
    FIX 2: Validates that dates and values lists are the same length before
            zip() — silently truncating mismatched lists would lose data.
    FIX 3: Distinguishes network/timeout errors (logger.error) from expected
            API failures (logger.warning) so severity is appropriate.
    FIX 4: Adds one retry with a short delay for transient 5xx failures.
    FIX 5: Adds Accept: application/json header as best practice.
    """
    params = {
        "latitude":     lat,
        "longitude":    lon,
        "daily":        "precipitation_sum",
        "timezone":     "Africa/Blantyre",
        "forecast_days": _FORECAST_DAYS,
    }
    headers = {
        "Accept": "application/json",
    }

    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = requests.get(
                _OPEN_METEO_URL,
                params=params,
                headers=headers,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            break   # success — exit retry loop

        except requests.exceptions.Timeout as exc:
            logger.error(
                "Open-Meteo request timed out (attempt %d/%d, lat=%.4f lon=%.4f): %s",
                attempt + 1, _MAX_RETRIES + 1, lat, lon, exc,
            )
            last_exc = exc

        except requests.exceptions.ConnectionError as exc:
            logger.error(
                "Open-Meteo connection error (attempt %d/%d, lat=%.4f lon=%.4f): %s",
                attempt + 1, _MAX_RETRIES + 1, lat, lon, exc,
            )
            last_exc = exc

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            if isinstance(status, int) and status >= 500:
                # Transient server error — retry
                logger.warning(
                    "Open-Meteo returned %s (attempt %d/%d) — retrying",
                    status, attempt + 1, _MAX_RETRIES + 1,
                )
                last_exc = exc
            else:
                # Client error (4xx) — no point retrying
                logger.warning(
                    "Open-Meteo HTTP %s for lat=%.4f lon=%.4f: %s",
                    status, lat, lon, exc,
                )
                return None

        except Exception as exc:
            logger.warning(
                "Open-Meteo unexpected error (lat=%.4f lon=%.4f): %s",
                lat, lon, exc,
            )
            return None

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_DELAY_S)
    else:
        # All attempts exhausted
        logger.error(
            "Open-Meteo failed after %d attempt(s) (lat=%.4f lon=%.4f): %s",
            _MAX_RETRIES + 1, lat, lon, last_exc,
        )
        return None

    try:
        data   = response.json()
        dates  = data["daily"]["time"]
        values = data["daily"]["precipitation_sum"]

        # FIX 2: validate list lengths before zip — mismatches are an API bug
        # but we must not silently truncate or pair wrong dates with wrong values
        if len(dates) != len(values):
            logger.error(
                "Open-Meteo returned mismatched dates (%d) and values (%d) "
                "for lat=%.4f lon=%.4f — discarding response",
                len(dates), len(values), lat, lon,
            )
            return None

        # Replace API nulls (no-rain days) with 0.0
        values = [v if v is not None else 0.0 for v in values]

        total = round(sum(values), 1)

        daily_forecast = [
            {"date": d, "mm": round(float(v), 1)}
            for d, v in zip(dates, values)
        ]

        return {
            "total_mm":       total,
            "daily_forecast": daily_forecast,
            "source":         "Open-Meteo (Live)",
        }

    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "Open-Meteo response parsing failed (lat=%.4f lon=%.4f): %s",
            lat, lon, exc,
        )
        return None


def get_live_rainfall_mm(lat: float, lon: float) -> int | None:
    """
    Convenience wrapper — returns total 7-day rainfall as a rounded integer,
    or None on failure.

    FIX: uses round() before int() so 4.9mm → 5 not 4.
    (int() truncates; round() gives the nearest integer.)
    """
    result = get_live_rainfall(lat, lon)
    if result is not None:
        return int(round(result["total_mm"]))
    return None