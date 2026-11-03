"""Safe, non-generative Groq connectivity check.

This calls only the authenticated model-list endpoint; it does not submit prompts.
"""
from collections.abc import Callable


def check_groq_connection(api_key: str, model_id: str, client_factory: Callable | None = None) -> dict[str, bool]:
    """Return booleans only; suppress provider exceptions and their potentially sensitive text."""
    try:
        if client_factory is None:
            from groq import Groq
            client_factory = Groq
        models = client_factory(api_key=api_key, timeout=10.0, max_retries=0).models.list()
        model_ids = {getattr(model, "id", None) for model in models.data}
        return {"reachable": True, "model_available": model_id in model_ids}
    except Exception:
        return {"reachable": False, "model_available": False}
