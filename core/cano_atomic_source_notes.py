"""Read-only, narrowly scoped numeric facts extracted from current source.

No code execution, network calls, stored feedback activation or inferred defaults.
Missing or ambiguous source expressions produce no fact.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


_TOPICS = {
    "source": re.compile(r"kaynak\s+bağlam|source\s+context", re.I),
    "benchmark": re.compile(r"benchmark|test\s+takımı|kıyaslama", re.I),
    "lesson": re.compile(r"ders\s+(?:benzerlik|tekrar|eşleşme)|lesson\s+(?:similarity|duplicate)", re.I),
}
_CANO = re.compile(r"\bCANO\b", re.I)
# file, function scope (None = module), expression, human-readable fact
_SPECS = {
    "lesson": (
        ("core/agent_colony.py", "AgentColony.approve_feedback", r"min\(len\(signature\), len\(prior\)\) >= (\d+)", "Yaklaşık ders eşleşmesi asgari metin uzunluğu"),
        ("core/agent_colony.py", "AgentColony.approve_feedback", r"SequenceMatcher\(None, signature, prior, autojunk=False\)\.ratio\(\) >= (0\.\d+|1\.0)", "Yaklaşık ders eşleşmesi oran eşiği"),
    ),
    "source": (
        ("core/cano_source_context.py", None, r"_MAX_FILE_CHARS = (\d+)", "Tek dosya alıntısı karakter sınırı"),
        ("core/cano_source_context.py", None, r"_MAX_TOTAL_CHARS = (\d+)", "Toplam kaynak bağlamı karakter sınırı"),
        ("core/cano_source_context.py", "build_cano_source_context", r"resolved\.stat\(\)\.st_size > (\d+)", "Okunabilir dosya azami boyutu"),
    ),
    "benchmark": (
        ("core/benchmark_harness.py", "_canonical_cases", r"len\(cases\) > (\d+)", "Genel benchmark azami vaka sayısı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"max_cases default = (\d+)", "max_cases varsayılanı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"1 <= max_cases <= (\d+)", "max_cases izin verilen üst sınırı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"len\(raw\) > (\d+)", "Ham JSON karakter sınırı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"len\(item\['case_id'\]\) > (\d+)", "Vaka kimliği karakter sınırı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"len\(item\['prompt'\]\) > (\d+)", "Soru metni karakter sınırı"),
        ("core/benchmark_harness.py", "parse_memory_benchmark_cases", r"len\(item\['expected'\]\) > (\d+)", "Beklenen cevap karakter sınırı"),
    ),
}


def atomic_source_topics(task: str) -> tuple[str, ...]:
    if not isinstance(task, str) or not _CANO.search(task):
        return ()
    return tuple(name for name, pattern in _TOPICS.items() if pattern.search(task))


def _read_tree(root: Path, relative: str):
    try:
        path = (root / relative).resolve(strict=True)
        path.relative_to(root)
        if not path.is_file() or path.stat().st_size > 200_000:
            return None
        return ast.parse(path.read_text(encoding="utf-8"), filename=relative)
    except (OSError, UnicodeError, ValueError, SyntaxError, RecursionError):
        return None


def _expressions(tree, function):
    if tree is None:
        return []
    if function is None:
        return [(ast.unparse(n), n.lineno) for n in tree.body
                if isinstance(n, ast.Assign)]
    body = tree.body
    if "." in function:
        class_name, function = function.split(".", 1)
        classes = [n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name]
        if len(classes) != 1:
            return []
        body = classes[0].body
    functions = [n for n in body if isinstance(n, ast.FunctionDef) and n.name == function]
    if len(functions) != 1:
        return []
    node = functions[0]
    result = [(ast.unparse(n), n.lineno) for n in ast.walk(node)
              if isinstance(n, ast.Compare)]
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if isinstance(default, ast.Constant) and type(default.value) is int:
            result.append((f"{arg.arg} default = {default.value}", default.lineno))
    return result


def build_atomic_source_notes(task: str, repo_root: str | Path) -> str:
    """Provide atomic facts with actual file/line provenance for explicit CANO topics."""
    topics = atomic_source_topics(task)
    if not topics:
        return ""
    root = Path(repo_root).resolve()
    trees = {}
    facts = []
    missing = 0
    for topic in topics:
        for relative, function, pattern, label in _SPECS[topic]:
            if relative not in trees:
                trees[relative] = _read_tree(root, relative)
            matches = []
            for expression, line in _expressions(trees[relative], function):
                match = re.fullmatch(pattern, expression)
                if match:
                    matches.append((match.group(1), line))
            if len(matches) == 1:
                value, line = matches[0]
                facts.append(f"- {relative}:{line} — {label}: {value}")
            else:
                missing += 1
    header = ("ATOMIC SOURCE NOTES (current read-only code; not runtime measurements). "
              "Use only relevant notes; cite their file and line. If a value is not "
              "supported, say it is unknown; never guess. These notes are not proof "
              "that tests were run or deployment succeeded.")
    if missing:
        facts.append(f"- {missing} requested-scope source facts unavailable/ambiguous; values unknown.")
    return header + "\n" + "\n".join(facts)
