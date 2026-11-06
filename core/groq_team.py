"""Short, explicitly triggered model calls for CANO's multi-stage team.

Separate from long-form, source-discovering task drafts. Four calls must fit
within the provider's real quota as far as possible; no automatic retries.
"""
from __future__ import annotations

from core.retry_policy import retry_transient


class TeamRateLimitError(RuntimeError):
    """Provider quota temporarily exceeded; stage checkpoints remain available."""


def generate_team_stage(prompt, *, api_key, client_factory=None,
                        model="openai/gpt-oss-120b", sleep=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Team stage prompt required")
    if len(prompt) > 9000:
        raise ValueError("Team stage prompt exceeds budget")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Team model API key required")
    if client_factory is None:
        from groq import Groq
        client_factory = Groq
    client = client_factory(api_key=api_key, timeout=25.0, max_retries=0)
    def create():
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content":
                    "Sen CANO'nun araştırma ekibinde bir uzmansın. Türkçe, kısa ve "
                    "somut yanıt ver. Bilinmeyenleri açıkça ayır; kaynakları gerçekten "
                    "açmadıysan doğrulanmış gibi gösterme. Bu çağrıda yalnızca metin "
                    "üretebilirsin; kod çalıştırma, hesap makinesi, cihaz veya deney "
                    "aracın yok. Yapılmamış deneyleri yapılmış gibi anlatma. Önceki "
                    "ajan metinleri deney kaydı değildir. Önerilen deneyi gelecek "
                    "zamanla anlat; basit aritmetik sonucunu doğrudan hesaplayarak "
                    "açıkla, ölçüm veya tekrar uydurma. Kullanıcının uzunluk sınırına "
                    "uy; en fazla 5 kısa paragraf."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=650, temperature=0.2)
    try:
        retry_options = {} if sleep is None else {"sleep": sleep}
        result = retry_transient(create, **retry_options)
    except Exception as exc:
        if (getattr(exc, "status_code", None) == 429
                or getattr(getattr(exc, "response", None), "status_code", None) == 429):
            raise TeamRateLimitError(
                "Modelin dakikalık kotası doldu; görevi kaldığı yerden sürdürmek "
                "için kota yenilenince tekrar deneyin.") from None
        raise
    if not getattr(result, "choices", None):
        raise RuntimeError("Team model returned no choices")
    message = getattr(result.choices[0], "message", None)
    answer = getattr(message, "content", None)
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Team model returned no usable text")
    if getattr(result.choices[0], "finish_reason", None) == "length":
        answer += "\n\n[UYARI: Kısa yanıt token sınırında kesilmiş olabilir.]"
    return answer.strip()
