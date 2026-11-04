"""Small safety helpers for the hosted, non-persistent lab demo."""
from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")


def session_output_dir(base: str | Path, session_state) -> Path:
    """Return a stable, isolated temporary directory for one Streamlit session."""
    session_id = session_state.get("organism_lab_session_id")
    if not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id):
        session_id = uuid4().hex
        session_state["organism_lab_session_id"] = session_id
    target = Path(base).resolve() / session_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def default_provider(*, cloud_mode: bool, environment=None) -> str:
    """Never assume local Ollama/LoRA exists in a hosted Render process."""
    env = os.environ if environment is None else environment
    if cloud_mode:
        return "groq" if bool(env.get("GROQ_API_KEY", "").strip()) else "offline"
    return "ollama"
