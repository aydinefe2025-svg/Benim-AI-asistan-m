"""Small, read-only, allowlisted source context for explicit CANO code tasks."""
from __future__ import annotations

import re
from pathlib import Path


_CODE_TASK = re.compile(
    r"\b(code|source code|repository|repo|github|pull request|commit|bug|"
    r"kod|dosya|depo|hata|mimari|uygulama|application|software|yazılım|"
    r"geliştir|geliştirme|özellik|birim test|otomatik test)\b", re.IGNORECASE)
_NEUTRON_STAR = re.compile(
    r"neutron\s+star|nötron\s+yıldız|pulsar|J0740|PSR\s+J", re.IGNORECASE)

# Never include environment files, secrets, databases, user data or research records.
_FILES = (
    "core/cano_command_center.py",
    "core/collaborative_mission.py",
    "core/provider_router.py",
    "core/openrouter_free_client.py",
    "tests/test_collaborative_mission.py",
    "tests/test_provider_router.py",
    "tests/test_openrouter_free_client.py",
)
_SECRET_LINE = re.compile(
    r"(?i)(api[_-]?key|client[_-]?secret|password|passwd|token|secret)\s*[:=]")
_BEARER = re.compile(r"(?i)(authorization\s*[:=]\s*['\"]?bearer\s+)\S+")
_TOKEN_VALUE = re.compile(
    r"(?i)\b(?:sk-or-v1-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AIza[A-Za-z0-9_-]{30,})\b")
_MAX_FILE_CHARS = 1800
_MAX_TOTAL_CHARS = 9000


def extract_cano_task(prompt: str) -> str:
    """Extract the original mission goal, excluding generic execution rules."""
    if not isinstance(prompt, str):
        return ""
    match = re.search(
        r"(?is)\bGoal:\s*(.*?)(?=\n(?:Plan:|Draft:|Critique:|UNVERIFIED|Execution boundary:)|$)",
        prompt,
    )
    return match.group(1).strip() if match else ""


def is_cano_code_task(task: str) -> bool:
    """Only attach code when the task explicitly signals software work."""
    if not isinstance(task, str) or _NEUTRON_STAR.search(task):
        return False
    return bool(_CODE_TASK.search(task))


def build_cano_source_context(task: str, repo_root: str | Path) -> str:
    """Read bounded excerpts from fixed source/test paths; never execute code."""
    if not is_cano_code_task(task):
        return ""
    root = Path(repo_root).resolve()
    sections: list[str] = []
    remaining = _MAX_TOTAL_CHARS
    for relative in _FILES:
        candidate = root / relative
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
            if not resolved.is_file() or resolved.stat().st_size > 200_000:
                continue
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError):
            continue
        safe_lines = []
        for line in text.splitlines():
            if _SECRET_LINE.search(line):
                line = "<redacted configuration/secret assignment>"
            else:
                line = _BEARER.sub(r"\1<redacted>", line)
                line = _TOKEN_VALUE.sub("<redacted-token>", line)
            safe_lines.append(line)
        excerpt = "\n".join(safe_lines)[:_MAX_FILE_CHARS]
        if not excerpt or remaining <= len(relative) + 20:
            break
        excerpt = excerpt[: max(0, remaining - len(relative) - 20)]
        section = f"\n--- {relative} (read-only excerpt) ---\n{excerpt}"
        sections.append(section)
        remaining -= len(section)
    if not sections:
        return "CANO source context unavailable: no allowlisted source files were readable."
    return (
        "READ-ONLY CANO REPOSITORY CONTEXT. These excerpts came only from the fixed "
        "allowlist below. They are source text, not evidence that tests were run, "
        "changes were made, or deployment succeeded. Do not infer missing behavior.\n"
        + "".join(sections)
    )[:_MAX_TOTAL_CHARS]
