"""Strict, bounded Groq JSON proposals for CANO's source quote audit.

The model cannot verify claims. The deterministic claim_evidence module still
checks verbatim quote presence and always records claim_verified=False.
"""
from __future__ import annotations

import json

from core.groq_team import TeamRateLimitError

_MODEL = "openai/gpt-oss-120b"
_VERIFICATION_MODEL = "openai/gpt-oss-120b"
_CLAIM_COMPLETION_LIMIT = 1100
_REVIEW_COMPLETION_LIMIT = 2400
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

_VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "verdict": {"type": "string", "enum": [
                        "supported", "contradicted", "insufficient"]},
                    "reason": {"type": "string"},
                },
                "required": ["index", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["assessments"],
    "additionalProperties": False,
}


def generate_claim_quote_json(system, prompt, *, api_key,
                              client_factory=None, model=_MODEL):
    """One strict-JSON provider call, no automatic chargeable retries."""
    return _generate_strict_json(
        system, prompt, _SCHEMA, "cano_claim_quote_proposals", "claims",
        api_key=api_key, client_factory=client_factory, model=model,
        max_completion_tokens=_CLAIM_COMPLETION_LIMIT)


def generate_claim_verification_json(system, prompt, *, api_key,
                                     client_factory=None, model=_VERIFICATION_MODEL):
    """A separate model's skeptical pass; it never sets claim_verified."""
    return _generate_strict_json(
        system, prompt, _VERIFICATION_SCHEMA, "cano_claim_evidence_assessments",
        "assessments", api_key=api_key, client_factory=client_factory, model=model,
        max_completion_tokens=_REVIEW_COMPLETION_LIMIT)


def _generate_strict_json(system, prompt, schema, schema_name, response_key, *,
                          api_key, client_factory=None, model=_MODEL,
                          max_completion_tokens=_CLAIM_COMPLETION_LIMIT):
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
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
            reasoning_format="hidden",
            reasoning_effort="low",
            max_completion_tokens=max_completion_tokens,
            temperature=0.2,
        )
    except Exception as exc:
        if (getattr(exc, "status_code", None) == 429
                or getattr(getattr(exc, "response", None), "status_code", None) == 429):
            raise TeamRateLimitError("Claim model request hit quota") from None
        # Never echo provider exceptions, which can contain URLs or credentials.
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status, int) and 400 <= status <= 599:
            detail = f"HTTP {status}"
        else:
            detail = type(exc).__name__
        raise RuntimeError(f"Claim JSON provider request failed ({detail})") from None
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
    if not isinstance(parsed, dict) or not isinstance(parsed.get(response_key), list):
        raise ValueError("Invalid claim JSON shape")
    return raw
