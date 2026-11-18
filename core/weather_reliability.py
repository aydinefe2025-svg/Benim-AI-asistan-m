"""Validate fresh current-weather data and preserve it if a text provider fails.

This module has no network access or LLM calls. It deliberately does not
interpret current conditions as a multi-day forecast.
"""
from __future__ import annotations

import re
from datetime import date, timedelta


_CITY = re.compile(r"[^\W\d_][\w .'-]{0,63}\Z", re.UNICODE)
_CONDITION = re.compile(r"[\w .,'()/-]{2,64}\Z", re.UNICODE)
_TEMPERATURE = re.compile(r"[+-]?\d{1,3}(?:[.,]\d)?°C\Z")
_HUMIDITY = re.compile(r"\d{1,3}%\Z")
_WIND = re.compile(r"[↗↘↖↙↑↓←→]?\d{1,3}(?:[.,]\d)?km/h\Z")
_WEATHER_QUESTION = re.compile(
    r"\b(?:hava|sıcaklık|sicaklik|derece|tahmin|tahminleri)\b", re.I
)
_CONTEXT = re.compile(
    r"HAVA SERVİSİ BİLGİSİ -> Şehir: (?P<city>[^|]+)"
    r" \| Durum: (?P<condition>[^|]+)"
    r" \| Sıcaklık: (?P<temperature>[^|]+)"
    r" \| Nem: (?P<humidity>[^|]+)"
    r" \| Rüzgar: (?P<wind>[^|\n]+)\.\Z"
)


def parse_wttr_current(city: str, raw: str) -> str | None:
    """Accept only complete, bounded fields from a delimited wttr.in response."""
    if (not isinstance(city, str) or not _CITY.fullmatch(city)
            or not isinstance(raw, str) or len(raw) > 240
            or any(char in raw for char in "\r\n<>" + chr(96))):
        return None
    fields = [part.strip() for part in raw.strip().split("|")]
    if len(fields) != 4:
        return None
    condition, temperature, humidity, wind = fields
    if not (_CONDITION.fullmatch(condition)
            and _TEMPERATURE.fullmatch(temperature)
            and _HUMIDITY.fullmatch(humidity)
            and 0 <= int(humidity[:-1]) <= 100
            and _WIND.fullmatch(wind)):
        return None
    return (
        f"HAVA SERVİSİ BİLGİSİ -> Şehir: {city}"
        f" | Durum: {condition} | Sıcaklık: {temperature}"
        f" | Nem: {humidity} | Rüzgar: {wind}."
    )


def weather_fallback_on_model_failure(question: str, weather_context: str) -> str | None:
    """Show only independently revalidated current weather, never fake forecasts."""
    if (not isinstance(question, str) or not _WEATHER_QUESTION.search(question)
            or not isinstance(weather_context, str)
            or len(weather_context) > 400):
        return None
    match = _CONTEXT.fullmatch(weather_context)
    if match is None:
        return None
    fields = match.groupdict()
    raw = "|".join((
        fields["condition"], fields["temperature"],
        fields["humidity"], fields["wind"],
    ))
    if parse_wttr_current(fields["city"], raw) != weather_context:
        return None
    return (
        weather_context.replace("HAVA SERVİSİ BİLGİSİ -> ", "Anlık hava verisi: ", 1)
        + "\n\nKaynak: wttr.in. Bu yalnızca anlık durum bilgisidir; "
        "ileri günlere ait hava tahminleri doğrulanmadı. "
        "Model sağlayıcısı yanıt veremediği için tahmin uydurmadım."
    )


# These helpers handle only weather prompts; regular chat and scientific
# research still use the existing evidence and model pipelines.
_FORECAST_REQUEST = re.compile(
    r"\b(?:tahmin(?:i|leri)?|yarın|yarin|haftalık|günlük)\b", re.I
)
_FORECAST_ROW = re.compile(
    r"(?P<day>\d{4}-\d{2}-\d{2}): en düşük (?P<minimum>-?\d{1,2})°C, "
    r"en yüksek (?P<maximum>-?\d{1,2})°C\Z"
)
_WEATHER_TOPIC = re.compile(
    r"\b(?:hava|sıcaklık|sicaklik|derece|yağış|yagis|rüzgar|ruzgar|"
    r"tahmin(?:i|leri)?)\b", re.I
)
_LOCATION_TOKEN = r"[A-Za-zÇĞİÖŞÜçğıöşü]+"
_NON_LOCATIONS = frozenset({
    "bugün", "yarın", "şimdi", "dışarıda", "burada", "nasıl", "kaç",
    "ne", "bizim", "bu", "için", "sabah", "akşam",
})


def weather_requested(question: str) -> bool:
    return isinstance(question, str) and bool(_WEATHER_TOPIC.search(question))


def forecast_requested(question: str) -> bool:
    return isinstance(question, str) and bool(_FORECAST_REQUEST.search(question))


def weather_location(question: str) -> str | None:
    """Accept an explicitly named city/district, never infer a user's location."""
    if not weather_requested(question):
        return None
    before = re.search(
        rf"({_LOCATION_TOKEN})(?:['’](?:da|de|ta|te))?\s+"
        r"(?:hava|sıcaklık|sicaklik|yağış|yagis|rüzgar|ruzgar)\b",
        question, re.I,
    )
    after = re.search(
        rf"\bhava(?:\s+(?:durumu|tahmin(?:i|leri)?))?\s+({_LOCATION_TOKEN})\b",
        question, re.I,
    )
    match = before or after
    if match is None:
        return None
    city = match.group(1)
    if city.casefold() in _NON_LOCATIONS or not _CITY.fullmatch(city):
        return None
    return city[0].upper() + city[1:]



def weather_region(question: str, city: str) -> str | None:
    """Extract an explicit province directly before the named weather city.

    Do not infer province from the account location, IP, or chat history.
    Temporal words ('yarın Ödemiş') are never treated as provinces.
    """
    if (not isinstance(question, str) or not isinstance(city, str)
            or not _CITY.fullmatch(city) or not weather_requested(question)):
        return None
    match = re.search(
        rf"(?P<region>{_LOCATION_TOKEN})\s+{re.escape(city)}"
        rf"(?:['’](?:da|de|ta|te))?\s+"
        r"(?:hava|sıcaklık|sicaklik|yağış|yagis|rüzgar|ruzgar|tahmin)\b",
        question, re.I,
    )
    if match is None:
        return None
    province = match.group("region")
    if province.casefold() in _NON_LOCATIONS or not _CITY.fullmatch(province):
        return None
    return province[0].upper() + province[1:]


def parse_wttr_forecast(city: str, data: object) -> str | None:
    """Fail closed on malformed or stale wttr.in j1 three-day forecast."""
    if not isinstance(city, str) or not _CITY.fullmatch(city):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("weather"), list):
        return None
    records = data["weather"]
    if not 1 <= len(records) <= 3:
        return None
    today = date.today()
    labels = []
    previous = None
    for record in records:
        if not isinstance(record, dict):
            return None
        day_value = record.get("date")
        minimum = record.get("mintempC")
        maximum = record.get("maxtempC")
        if (not isinstance(day_value, str)
                or not isinstance(minimum, str)
                or not isinstance(maximum, str)
                or not re.fullmatch(r"-?\d{1,2}", minimum)
                or not re.fullmatch(r"-?\d{1,2}", maximum)):
            return None
        try:
            day = date.fromisoformat(day_value)
        except ValueError:
            return None
        low, high = int(minimum), int(maximum)
        if (not today - timedelta(days=1) <= day <= today + timedelta(days=4)
                or (previous is not None and day <= previous)
                or not -60 <= low <= high <= 60):
            return None
        labels.append(f"{day.isoformat()}: en düşük {low}°C, en yüksek {high}°C")
        previous = day
    return "HAVA TAHMİNİ -> Şehir: " + city + "\n" + "\n".join(labels)


def weather_direct_reply(question: str, source: str) -> str | None:
    """Return source-validated weather without sending it through scholarly RAG/LLM."""
    if not weather_requested(question):
        return None
    if isinstance(source, str) and source.startswith("HAVA TAHMİNİ -> Şehir: "):
        lines = source.split("\n")
        city = lines[0].removeprefix("HAVA TAHMİNİ -> Şehir: ")
        records = []
        for line in lines[1:]:
            match = _FORECAST_ROW.fullmatch(line)
            if match is None:
                break
            records.append({
                "date": match.group("day"),
                "mintempC": match.group("minimum"),
                "maxtempC": match.group("maximum"),
            })
        if len(records) == len(lines) - 1 and parse_wttr_forecast(
            city, {"weather": records}
        ) == source:
            return source.replace("HAVA TAHMİNİ ->", "Doğrulanmış hava tahmini:", 1) + (
                "\n\nKaynak: wttr.in (günlük hava tahmini; kesin ölçüm değil)."
            )
    # Open-Meteo is a separate model-data provider, never a wttr.in quote.
    # The envelope is revalidated before any value reaches the user.
    from core.open_meteo_weather import render_open_meteo_reply
    backup_answer = render_open_meteo_reply(question, source)
    if backup_answer is not None:
        return backup_answer
    if isinstance(source, str):
        current = weather_fallback_on_model_failure(question, source)
        if current is not None:
            summary = current.split("\n\nKaynak:", 1)[0]
            message = "\n\nKaynak: wttr.in. Bu yalnızca anlık hava verisidir."
            if forecast_requested(question):
                message += " Gelecek günlere ait tahmin alınamadı; uydurulmadı."
            return summary + message
    if weather_location(question) is None:
        return "Hava durumu için şehir veya ilçe adını yaz; konumunu tahmin etmiyorum."
    return "Hava servisine ulaşılamadı veya hava verileri doğrulanamadı; tahmin uydurmadım."
