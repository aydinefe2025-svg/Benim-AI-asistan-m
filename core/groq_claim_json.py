"""Strict, bounded Groq JSON proposals for CANO's source quote audit.

The model cannot verify claims. The deterministic claim_evidence module still
checks verbatim quote presence and always records claim_verified=False.
"""
from __future__ import annotations

import json

from core.groq_team import TeamRateLimitError

_MODEL = "openai/gpt-oss-120b"
_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "doi": {"type": "string"},
                    "quote": {"type": "string"},
                    "comparison": {
                        "type": "string",
                        "enum": ["supports", "contradicts", "correction_or_context", "insufficient"],
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["claim", "doi", "quote", "comparison", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def generate_claim_quote_json(system, prompt, *, api_key,
                              client_factory=None, model=_MODEL):
    """One strict-JSON provider call, no automatic chargeable retries."""
    if (not isinstance(system, str) or not isinstance(prompt, str)
            or not system.strip() or not prompt.strip()
            or len(system) + len(prompt) > 9000):
        raise ValueError("Invalid or oversized claim JSON prompt")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("Claim JSON provider key is unavailable")
    if client_factory is None:
        from groq import Groq
        client_factory = Groq
    client = client_factory(api_key=api_key, timeout=25.0, max_retries=0)
    try:
        result = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system + "\nOutput valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "cano_claim_quote_proposals",
                    "strict": True,
                    "schema": _SCHEMA,
                },
            },
            reasoning_format="hidden",
            reasoning_effort="low",
            max_completion_tokens=1100,
            temperature=0.2,
        )
    except Exception as exc:
        if (getattr(exc, "status_code", None) == 429
                or getattr(getattr(exc, "response", None), "status_code", None) == 429):
            raise TeamRateLimitError("Claim model request hit quota") from None
        # Never echo provider exceptions, which can contain URLs or credentials.
        raise RuntimeError("Claim JSON provider request failed") from None
    choices = getattr(result, "choices", None)
    if not choices:
        raise RuntimeError("Claim JSON provider returned no choices")
    if getattr(choices[0], "finish_reason", None) == "length":
        raise RuntimeError("Claim JSON response was truncated")
    message = getattr(choices[0], "message", None)
    raw = getattr(message, "content", None)
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 6000:
        raise ValueError("Invalid claim JSON response")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("Invalid claim JSON response") from None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("claims"), list):
        raise ValueError("Invalid claim JSON shape")
    return raw
