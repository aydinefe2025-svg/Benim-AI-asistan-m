"""Bounded deterministic arithmetic for explicit owner-selected chat commands."""
import re
import unicodedata

_PREFIX = re.compile(r"cano[ \t]+hesap[ \t]*:", re.IGNORECASE)
_ERROR = ("CANO hesap: geçersiz işlem. Örnek: CANO hesap: çıkar 93 56. "
          "Tam sayı sınırı ±1.000.000; bölme tam sonuç vermelidir.")


def explicit_calculation_reply(message):
    """Return None for ordinary chat; never infer operands from model output."""
    if not isinstance(message, str):
        return None
    command = message.strip(" \t")
    prefix = _PREFIX.match(command)
    if prefix is None:
        return None
    if len(command) > 80 or not command.isascii() and any(
        ch.isdigit() and ch not in "0123456789" for ch in command
    ):
        return _ERROR
    parsed = re.fullmatch(r"[ \t]*([^ \t]+)[ \t]+(-?[0-9]{1,7})[ \t]+(-?[0-9]{1,7})[ \t]*", command[prefix.end():])
    if parsed is None:
        return _ERROR
    op, left, right = parsed.groups()
    op = unicodedata.normalize("NFKD", op.casefold())
    op = "".join(ch for ch in op if not unicodedata.combining(ch)).replace("ı", "i")
    if op not in ("topla", "cikar", "carp", "bol"):
        return _ERROR
    a, b = int(left), int(right)
    if abs(a) > 10**6 or abs(b) > 10**6:
        return _ERROR
    if op == "topla":
        return str(a + b)
    if op == "cikar":
        return str(a - b)
    if op == "carp":
        return str(a * b)
    if b == 0 or a % b:
        return _ERROR
    return str(a // b)
