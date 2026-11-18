"""Validated current-weather source and fallback when a text model fails.

This module never fetches weather or invokes a model. It only validates a bounded
service response and protects source provenance at the app boundary.
"""


def parse_wttr_current(city: str, raw: str) -> str | None:
    """Return a canonical weather context only for complete, safe values."""
    return None


def weather_fallback_on_model_failure(question: str, weather_context: str) -> str | None:
    """Use validated current weather without claiming a forecast."""
    return None
