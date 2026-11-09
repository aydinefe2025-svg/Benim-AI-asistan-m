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


def failure_category(error):
    kind = getattr(error, "failure_kind", None)
    if kind in MESSAGES:
        return kind
    status = getattr(error, "status_code", None)
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
