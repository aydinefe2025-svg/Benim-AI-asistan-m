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


def failure_category(error):
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
    # Only consume known machine codes, never arbitrary provider messages.
    body = getattr(error, "body", None)
    detail = body.get("error", body) if isinstance(body, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
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
    if kind not in allowed:
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
