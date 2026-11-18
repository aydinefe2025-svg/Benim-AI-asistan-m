"""Independently validated Open-Meteo weather backup for CANO.

Only explicit weather questions reach this provider. No model, paid service,
owner identity, memory or other conversation content is sent to these URLs.
All third-party JSON is checked before being returned to the chat renderer.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
import math
import re
import unicodedata


_PREFIX = "OPEN_METEO_JSON:"
_CITY = re.compile(r"[^\W\d_][\w .'-]{0,63}\Z", re.UNICODE)
_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ALLOWED_KEYS = frozenset({
    "provider", "city", "time", "utc_offset_seconds", "temperature",
    "humidity", "wind", "weather_code", "daily",
})
_WMO = {
    0: "Açık", 1: "Çoğunlukla açık", 2: "Parçalı bulutlu", 3: "Bulutlu",
    45: "Sisli", 48: "Kırağılı sis", 51: "Hafif çiseleme",
    53: "Çiseleme", 55: "Yoğun çiseleme", 56: "Donan çiseleme",
    57: "Yoğun donan çiseleme", 61: "Hafif yağmur", 63: "Yağmur",
    65: "Şiddetli yağmur", 66: "Donan yağmur", 67: "Yoğun donan yağmur",
    71: "Hafif kar", 73: "Kar", 75: "Yoğun kar", 77: "Kar taneleri",
    80: "Hafif sağanak", 81: "Sağanak", 82: "Şiddetli sağanak",
    85: "Kar sağanağı", 86: "Yoğun kar sağanağı",
    95: "Gök gürültülü fırtına", 96: "Dolu ihtimalli fırtına",
    99: "Şiddetli dolulu fırtına",
}


def _norm(name):
    if not isinstance(name, str):
        return ""
    return "".join(
        char for char in unicodedata.normalize(
            "NFKD", name.casefold().replace("ı", "i")
        ) if not unicodedata.combining(char)
    )


def _number(value, low, high):
    if type(value) not in (float, int) or not math.isfinite(value):
        return False
    return low <= value <= high


def _geo_location(city, response, *, province=None):
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        return None
    matches = []
    for entry in response["results"][:10]:
        if not isinstance(entry, dict):
            continue
        if _norm(entry.get("name")) != _norm(city):
            continue
        lat, lon = entry.get("latitude"), entry.get("longitude")
        if not _number(lat, -90, 90) or not _number(lon, -180, 180):
            continue
        matches.append(entry)
    local = [e for e in matches if e.get("country_code") == "TR"]
    choices = local if local else matches
    if province is not None:
        # An explicitly named province wins only when exactly one matching
        # location exists. Do not silently fall back to a different province.
        choices = [
            e for e in local
            if _norm(e.get("admin1")) == _norm(province)
        ]
    elif len(choices) > 1:
        # One town may share its name with several hamlets in other provinces.
        # Select only a uniquely named administrative district when provable.
        district = _norm(city + " İlçesi")
        choices = [
            e for e in choices
            if _norm(e.get("admin2")) == district
        ]
    if len(choices) != 1:
        return None
    return choices[0]["latitude"], choices[0]["longitude"]


def _verified_context(value):
    if (not isinstance(value, str)
            or not value.startswith(_PREFIX) or len(value) > 2200):
        return None
    try:
        raw = json.loads(value[len(_PREFIX):])
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or set(raw) != _ALLOWED_KEYS:
        return None
    city = raw["city"]
    if raw["provider"] != "Open-Meteo" or not isinstance(city, str):
        return None
    if not _CITY.fullmatch(city) or len(city) > 64:
        return None
    offset = raw["utc_offset_seconds"]
    stamp = raw["time"]
    if type(offset) is not int or not -43200 <= offset <= 50400:
        return None
    if not isinstance(stamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?", stamp
    ):
        return None
    try:
        local_as_utc = datetime.fromisoformat(stamp).replace(
            tzinfo=timezone(timedelta(seconds=offset))
        ).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None
    age = (datetime.now(timezone.utc) - local_as_utc).total_seconds()
    if not -3600 <= age <= 10800:
        return None
    if (not _number(raw["temperature"], -90, 65)
            or not _number(raw["humidity"], 0, 100)
            or not _number(raw["wind"], 0, 350)):
        return None
    code = raw["weather_code"]
    if type(code) is not int or code not in _WMO:
        return None

    days = raw["daily"]
    if not isinstance(days, list) or len(days) > 3:
        return None
    today = (datetime.now(timezone.utc) + timedelta(seconds=offset)).date()
    for i, item in enumerate(days):
        if not isinstance(item, dict) or set(item) != {"date", "min", "max"}:
            return None
        d, low, high = item["date"], item["min"], item["max"]
        if not isinstance(d, str):
            return None
        try:
            day = date.fromisoformat(d)
        except ValueError:
            return None
        if day != today + timedelta(days=i):
            return None
        if (not _number(low, -90, 65) or not _number(high, -90, 65)
                or low > high):
            return None
    return raw


def fetch_open_meteo_weather(city, *, get, forecast=False, province=None):
    """Return an internal, bounded source envelope; never a raw API answer.

    The injected HTTP GET seam permits independent offline regression tests.
    Only requested city is sent to geocoding; no chat history or owner token.
    """
    if not isinstance(city, str) or not _CITY.fullmatch(city):
        return None
    if province is not None and (
        not isinstance(province, str) or not _CITY.fullmatch(province)
    ):
        return None
    try:
        geo_response = get(
            _GEO_URL,
            params={"name": city, "count": 10, "language": "tr", "format": "json"},
            timeout=5,
        )
        if geo_response.status_code != 200:
            return None
        coords = _geo_location(city, geo_response.json(), province=province)
        if coords is None:
            return None
        latitude, longitude = coords
        parameters = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "wind_speed_10m,weather_code"
            ),
            "timezone": "auto",
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
        }
        if forecast:
            parameters["daily"] = "temperature_2m_min,temperature_2m_max"
            parameters["forecast_days"] = 3
        response = get(_FORECAST_URL, params=parameters, timeout=6)
        if response.status_code != 200:
            return None
        body = response.json()
        if not isinstance(body, dict):
            return None
        current = body.get("current")
        units = body.get("current_units")
        if not isinstance(current, dict) or not isinstance(units, dict):
            return None
        if any((
            units.get("temperature_2m") != "°C",
            units.get("relative_humidity_2m") != "%",
            units.get("wind_speed_10m") != "km/h",
        )):
            return None
        days = []
        if forecast:
            daily = body.get("daily")
            daily_units = body.get("daily_units")
            if (isinstance(daily, dict)
                    and isinstance(daily_units, dict)
                    and daily_units.get("temperature_2m_min") == "°C"
                    and daily_units.get("temperature_2m_max") == "°C"):
                dates = daily.get("time")
                minimums = daily.get("temperature_2m_min")
                maximums = daily.get("temperature_2m_max")
                if (isinstance(dates, list)
                        and isinstance(minimums, list)
                        and isinstance(maximums, list)
                        and len(dates) == len(minimums) == len(maximums) == 3):
                    days = [
                        {"date": day, "min": low, "max": high}
                        for day, low, high in zip(dates, minimums, maximums)
                    ]
        envelope = {
            "provider": "Open-Meteo",
            "city": city,
            "time": current.get("time"),
            "utc_offset_seconds": body.get("utc_offset_seconds"),
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "daily": days,
        }
        result = _PREFIX + json.dumps(
            envelope, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
        return result if _verified_context(result) is not None else None
    except (Exception):
        # Network outages, unexpected JSON shapes and data type errors are
        # fail-closed. Do not leak upstream bodies, locations or credentials.
        return None


def render_open_meteo_reply(question, context):
    """Return verified, current, attributed model weather, never Crossref or LLM."""
    from core.weather_reliability import weather_location, forecast_requested
    fields = _verified_context(context)
    city = weather_location(question)
    if fields is None or city is None or _norm(city) != _norm(fields["city"]):
        return None
    description = _WMO[fields["weather_code"]]
    summary = (
        f"{fields['city']} için güncel model hava verisi "
        f"({fields['time']} yerel saat): {description}. "
        f"Sıcaklık {fields['temperature']:.1f}°C, "
        f"nem %{fields['humidity']:.0f}, "
        f"rüzgâr {fields['wind']:.1f} km/sa."
    )
    if forecast_requested(question):
        if fields["daily"]:
            summary += "\n\n3 günlük tahmin (model):"
            for entry in fields["daily"]:
                summary += (
                    f"\n{entry['date']}: en düşük {entry['min']:.1f}°C, "
                    f"en yüksek {entry['max']:.1f}°C"
                )
        else:
            summary += (
                "\nGelecek günlere ait doğrulanmış tahmin bulunamadı."
            )
    return (
        summary + "\n\nKaynak: Open-Meteo (sayısal hava modeli; "
        "istasyon gözlemi veya kesin tahmin değildir)."
    )
