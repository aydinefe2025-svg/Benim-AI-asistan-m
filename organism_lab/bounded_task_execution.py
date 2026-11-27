"""Safe, finite, offline CANO task primitives for experimental capability evaluation.

This is NOT a general AI agent and does not execute user-supplied Python.
Results are candidates only until an independently supplied oracle accepts them.
"""
from __future__ import annotations
import ast
import csv
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import io
import json
from collections import defaultdict

MAX_JOB_BYTES = 32_768
LENGTH_FACTORS = {"mm": Decimal("0.001"), "cm": Decimal("0.01"),
                  "m": Decimal("1"), "km": Decimal("1000")}
MASS_FACTORS = {"mg": Decimal("0.000001"), "g": Decimal("0.001"),
                "kg": Decimal("1")}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("numeric input must be an integer or decimal string")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite() or abs(result) > Decimal("1e12"):
        raise ValueError("unbounded numeric input")
    return result


def _decimal_text(value):
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _csv_mean(job):
    content = job.get("csv")
    group = job.get("group_column")
    field = job.get("value_column")
    if not isinstance(content, str) or len(content) > 16000:
        raise ValueError("CSV missing or oversized")
    if not isinstance(group, str) or not isinstance(field, str) or group == field:
        raise ValueError("invalid CSV columns")
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or group not in reader.fieldnames or field not in reader.fieldnames:
        raise ValueError("CSV columns missing")
    sums, counts = defaultdict(Decimal), defaultdict(int)
    for row in reader:
        if len(row) != len(reader.fieldnames) or None in row:
            raise ValueError("malformed CSV row")
        key = row.get(group)
        if key is None or key == "":
            raise ValueError("empty group")
        sums[key] += _number(row.get(field))
        counts[key] += 1
        if sum(counts.values()) > 128:
            raise ValueError("CSV row budget exceeded")
    if not counts:
        raise ValueError("empty CSV")
    return {key: _decimal_text(sums[key] / counts[key]) for key in sorted(counts)}


def _json_pointer(job):
    document = job.get("document")
    pointer = job.get("pointer")
    if not isinstance(pointer, str) or len(pointer) > 512 or (pointer and not pointer.startswith("/")):
        raise ValueError("invalid JSON pointer")
    current = document
    if pointer:
        for raw in pointer.split("/")[1:]:
            # Reject illegal RFC6901 escapes rather than silently misreading.
            import re
            if re.search(r"~(?![01])", raw):
                raise ValueError("invalid JSON pointer escape")
            key = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if key not in current:
                    raise ValueError("JSON key missing")
                current = current[key]
            elif isinstance(current, list):
                if not key.isdecimal() or (len(key) > 1 and key.startswith("0")):
                    raise ValueError("invalid JSON array index")
                index = int(key)
                if not 0 <= index < len(current):
                    raise ValueError("JSON array index absent")
                current = current[index]
            else:
                raise ValueError("JSON pointer traverses scalar")
    return current


def _convert_unit(job):
    src, dst = job.get("from_unit"), job.get("to_unit")
    matching = None
    for table in (LENGTH_FACTORS, MASS_FACTORS):
        if src in table and dst in table:
            matching = table
            break
    if matching is None:
        raise ValueError("unknown or dimension-incompatible units")
    converted = _number(job.get("value")) * matching[src] / matching[dst]
    return _decimal_text(converted)


def _fit_linear(job):
    points = job.get("points")
    if not isinstance(points, list) or not 2 <= len(points) <= 128:
        raise ValueError("linear fit requires 2..128 points")
    xs, ys = [], []
    for item in points:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("invalid point")
        xs.append(Fraction(_number(item[0])))
        ys.append(Fraction(_number(item[1])))
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    d = n * sum(x*x for x in xs) - sx*sx
    if d == 0:
        raise ValueError("linear fit undefined for identical x values")
    m = (n * sum(x*y for x, y in zip(xs, ys)) - sx*sy) / d
    b = (sy - m*sx)/n
    return {"slope": [m.numerator, m.denominator], "intercept": [b.numerator, b.denominator]}


def _repair_python(job):
    original = job.get("source")
    if not isinstance(original, str) or len(original) > 4096:
        raise ValueError("Python source missing or oversized")
    if job.get("bug_type") != "off_by_one_range":
        raise ValueError("unsupported repair claim")
    try:
        tree = ast.parse(original)
    except SyntaxError as exc:
        raise ValueError("source is not valid Python") from exc
    if any(isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                             ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
           for node in ast.walk(tree)):
        raise ValueError("unsafe/ambiguous source for static patch")
    target = "range(1, len("
    if original.count(target) != 1:
        raise ValueError("ambiguous or absent single static patch")
    patched = original.replace(target, "range(len(", 1)
    try:
        ast.parse(patched)
    except SyntaxError as exc:
        raise ValueError("invalid patched syntax") from exc
    return patched


def _verify_exact_quote(job):
    source = job.get("source_text")
    quote = job.get("quote")
    source_id = job.get("source_id")
    if not isinstance(source, str) or not 0 < len(source) <= 16000:
        raise ValueError("source text missing or oversized")
    if not isinstance(quote, str) or not 0 < len(quote) <= 256:
        raise ValueError("quote missing or oversized")
    if not isinstance(source_id, str) or not 0 < len(source_id) <= 128:
        raise ValueError("source ID required")
    return {"support_level": "exact_quote" if quote in source else "unverified",
            "source_id": source_id,
            "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}


def _legacy_csv_mean(job):
    values = job.get("values")
    if not isinstance(values, list) or not 1 <= len(values) <= 128:
        raise ValueError("CSV values missing or over budget")
    if any(type(x) is not int or abs(x) > 10**9 for x in values):
        raise ValueError("invalid CSV values")
    return sum(values) / len(values)


def _legacy_json_lookup(job):
    data, path = job.get("data"), job.get("path")
    if not isinstance(path, list) or not 1 <= len(path) <= 32:
        raise ValueError("invalid nested path")
    current = data
    for segment in path:
        if not isinstance(segment, str) or len(segment) > 128:
            raise ValueError("invalid path segment")
        if not isinstance(current, dict) or segment not in current:
            raise ValueError("nested key missing")
        current = current[segment]
    return current


def _legacy_unit(job):
    amount = job.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
        raise ValueError("invalid unit amount")
    # Float inputs are normalized to a decimal string before exact conversion.
    converted = _convert_unit({"value": str(amount),
                               "from_unit": job.get("from"), "to_unit": job.get("to")})
    return float(converted)


def _legacy_slope(job):
    answer = _fit_linear(job)["slope"]
    return answer[0] / answer[1]


def _legacy_python_fix(job):
    original, specification = job.get("source"), job.get("test")
    if not isinstance(original, str) or len(original) > 2048:
        raise ValueError("source missing or oversized")
    if not isinstance(specification, str) or len(specification) > 128:
        raise ValueError("test specification missing")
    # Only a precisely verified and statically inspectable add(a,b) defect.
    import re
    match = re.fullmatch(r"add\((-?\d+),(-?\d+)\)==(-?\d+)", specification.replace(" ",""))
    if match is None:
        raise ValueError("unsupported code repair specification")
    a,b,c = map(int, match.groups())
    if not (a + b == c and a - b != c):
        raise ValueError("specification does not establish subtraction defect")
    tree = ast.parse(original)
    if (len(tree.body) != 1 or not isinstance(tree.body[0],ast.FunctionDef)
        or tree.body[0].name != "add" or len(tree.body[0].body) != 1
        or [n.arg for n in tree.body[0].args.args] != ["a","b"]
        or not isinstance(tree.body[0].body[0],ast.Return)):
        raise ValueError("unsupported Python structure")
    node=tree.body[0].body[0].value
    if not (isinstance(node,ast.BinOp) and isinstance(node.op,ast.Sub)
            and isinstance(node.left,ast.Name) and node.left.id=="a"
            and isinstance(node.right,ast.Name) and node.right.id=="b"):
        raise ValueError("ambiguous source for static correction")
    return "return a+b"


def _legacy_source_check(job):
    claim = job.get("claim")
    sources = job.get("sources")
    required = job.get("must_peer_review")
    if not isinstance(claim,str) or not claim or len(claim)>512:
        raise ValueError("claim missing or oversized")
    if not isinstance(required,bool) or not isinstance(sources,list) or not 1 <= len(sources)<=10:
        raise ValueError("source metadata missing")
    for item in sources:
        if not isinstance(item,dict) or not isinstance(item.get("id"),str):
            raise ValueError("source ID missing")
        text=item.get("text")
        reviewed=item.get("peer_reviewed")
        if not isinstance(text,str) or len(text)>8192 or not isinstance(reviewed,bool):
            raise ValueError("unvalidated source metadata")
        if claim in text and (not required or reviewed):
            return True
    # This is only metadata/literal consistency, not externally authenticated scholarship.
    return False


DISPATCH = {
    "csv_mean": _legacy_csv_mean,
    "json_nested_lookup": _legacy_json_lookup,
    "unit_conversion": _legacy_unit,
    "linear_fit_slope": _legacy_slope,
    "python_bug_fix": _legacy_python_fix,
    "source_citation_check": _legacy_source_check,
    "csv_group_mean": _csv_mean,
    "json_pointer": _json_pointer,
    "convert_unit": _convert_unit,
    "fit_linear": _fit_linear,
    "repair_python": _repair_python,
    "verify_exact_quote": _verify_exact_quote,
}


def execute(job):
    if not isinstance(job, dict):
        raise ValueError("task must be a dictionary")
    try:
        encoded = json.dumps(job, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("task cannot be serialized") from exc
    if len(encoded) > MAX_JOB_BYTES:
        raise ValueError("task byte budget exceeded")
    kind = job.get("type")
    if kind not in DISPATCH:
        raise ValueError("unsupported task type")
    return DISPATCH[kind](job)


def _oracle_equal(candidate, expected, *, depth=0):
    """Compare JSON-like values without Python bool/int equivalence or nonfinite numbers."""
    if depth > 20:
        return False
    if isinstance(candidate, bool) or isinstance(expected, bool):
        return type(candidate) is bool and type(expected) is bool and candidate is expected
    if isinstance(candidate, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        try:
            a, b = Decimal(str(candidate)), Decimal(str(expected))
        except InvalidOperation:
            return False
        return a.is_finite() and b.is_finite() and a == b
    if isinstance(candidate, str) and isinstance(expected, str):
        return candidate == expected
    if candidate is None or expected is None:
        return candidate is expected
    if isinstance(candidate, dict) and isinstance(expected, dict):
        if candidate.keys() != expected.keys():
            return False
        return all(_oracle_equal(candidate[key], expected[key], depth=depth + 1)
                   for key in candidate)
    if isinstance(candidate, list) and isinstance(expected, list):
        return len(candidate) == len(expected) and all(
            _oracle_equal(a, b, depth=depth + 1) for a, b in zip(candidate, expected))
    return False


def gate_result(result, expected=None):
    """Never mark a worker assertion verified without an independent oracle value."""
    if expected is None:
        return {"status": "unverified"}
    return {"status": "verified" if _oracle_equal(result, expected) else "rejected"}
