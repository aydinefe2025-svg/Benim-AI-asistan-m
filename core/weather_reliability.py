"""Validate fresh current-weather data and preserve it if a text provider fails.

This module has no network access or LLM calls. It deliberately does not
interpret current conditions as a multi-day forecast.
"""
from __future__ import annotations

import re


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
