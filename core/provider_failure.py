"""Allowlisted provider failure categories; never display exception text/body."""


MESSAGES = {
    "authentication": "API anahtarı reddedildi; güvenli ortam ayarındaki anahtarı kontrol edin.",
    "permission": "Sağlayıcı bu işlem için erişim izni vermiyor.",
    "rate_limit": "Sağlayıcı kota veya istek sınırına ulaşıldığını bildirdi; daha sonra yeniden deneyin.",
    "model": "Seçili model bulunamadı veya kullanımdan kaldırıldı; model ayarını kontrol edin.",
    "request": "Sağlayıcı isteği kabul etmedi; model ve istek ayarlarını kontrol edin.",
    "network": "Sağlayıcıya ağ bağlantısı kurulamadı veya bağlantı zaman aşımına uğradı.",
    "service": "Model hizmeti geçici olarak kullanılamıyor; daha sonra yeniden deneyin.",
    "response": "Sağlayıcı yanıtı boş veya biçimi geçersizdi.",
    "storage": "Öğrenme kaydı kalıcı depoya yazılamadı; mevcut dersler korunuyor.",
    "unknown": "Model yanıtı alınamadı; bağlantı ve model ayarlarını kontrol edin.",
}


def _http_status(error):
    """Read only canonical numeric HTTP status fields from provider exceptions."""
    for field in ("status_code", "code"):
        status = getattr(error, field, None)
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            return status
    return None


SAFE_PROVIDER_ERROR_CODES = {
    "model_not_found", "model_decommissioned", "invalid_request_error",
    "unsupported_parameter", "context_length_exceeded", "request_too_large",
    "invalid_api_key", "insufficient_quota", "rate_limit_exceeded",
    "content_policy_violation", "server_error",
}


def _provider_error_code(error):
    """Return only an allowlisted provider machine code or error type."""
    code = getattr(error, "failure_code", None)
    if not isinstance(code, str) or code not in SAFE_PROVIDER_ERROR_CODES:
        body = getattr(error, "body", None)
        detail = body.get("error", body) if isinstance(body, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else None
        if not isinstance(code, str) or code not in SAFE_PROVIDER_ERROR_CODES:
            code = detail.get("type") if isinstance(detail, dict) else None
    return code if isinstance(code, str) and code in SAFE_PROVIDER_ERROR_CODES else None


def failure_diagnostics(error):
    """Expose only numeric HTTP status and allowlisted code for logs."""
    return _http_status(error), _provider_error_code(error)


def failure_category(error):
    # Some gateways encode exhausted quota as HTTP 413 rather than 429.
    # A specific allowlisted machine code must win over that ambiguous status.
    code = _provider_error_code(error)
    if code in ("insufficient_quota", "rate_limit_exceeded"):
        return "rate_limit"
    kind = getattr(error, "failure_kind", None)
    if kind in MESSAGES:
        return kind
    status = _http_status(error)
    if status == 401:
        return "authentication"
    if status == 403:
        return "permission"
    if status == 429:
        return "rate_limit"
    if status == 404 or code in ("model_not_found", "model_decommissioned"):
        return "model"
    if status in (400, 413, 422):
        return "request"
    if status in (408, 504) or isinstance(error, (TimeoutError, ConnectionError)) or type(error).__name__ in (
        "APIConnectionError", "APITimeoutError", "ConnectTimeout", "ReadTimeout",
    ):
        return "network"
    if isinstance(status, int) and 500 <= status <= 599:
        return "service"
    return "unknown"


def safe_failure_message(error):
    return MESSAGES[failure_category(error)]


def copy_safe_failure_metadata(source, target):
    """Copy only canonical status metadata; never copy provider message/body text."""
    kind = getattr(source, "failure_kind", None)
    allowed = set(MESSAGES)
    status = _http_status(source)
    code = _provider_error_code(source)
    if code in ("insufficient_quota", "rate_limit_exceeded"):
        kind = "rate_limit"
    elif kind not in allowed:
        if status == 401:
            kind = "authentication"
        elif status == 403:
            kind = "permission"
        elif status == 429:
            kind = "rate_limit"
        elif status == 404:
            kind = "model"
        elif status in (400, 413, 422):
            kind = "request"
        elif (status in (408, 504)
              or isinstance(source, (TimeoutError, ConnectionError))
              or type(source).__name__ in (
                  "APIConnectionError", "APITimeoutError", "ConnectTimeout",
                  "ReadTimeout")):
            kind = "network"
        elif isinstance(status, int) and 500 <= status <= 599:
            kind = "service"
        elif isinstance(source, ValueError):
            kind = "response"
        else:
            kind = "unknown"
    target.failure_kind = kind
    if status is not None:
        target.status_code = status
    if code is not None:
        target.failure_code = code
