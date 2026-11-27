"""Exact arithmetic for a deliberately narrow, explicit Turkish count contract.

No model, external source or expression evaluation is needed. Unrecognized
or inconsistent tasks fall through to the normal agent path.
"""
import re

_ONES = ("sıfır", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_ONES_PART = ("sıfırı", "biri", "ikisi", "üçü", "dördü", "beşi", "altısı", "yedisi", "sekizi", "dokuzu")
_TENS = ("", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan")
_TENS_PART = ("", "onu", "yirmisi", "otuzu", "kırkı", "ellisi", "altmışı", "yetmişi", "sekseni", "doksanı")
_NOUNS = {
    "kaydın": "kayıt", "dosyanın": "dosya", "belgenin": "belge",
    "örneğin": "örnek", "ölçümün": "ölçüm", "cihazın": "cihaz",
    "parçanın": "parça", "elemanın": "eleman", "bileşenin": "bileşen",
}
_WORD = r"[a-zçğıöşü]+(?: [a-zçğıöşü]+)?"
_PATTERN = re.compile(
    rf"(?P<total>[0-9]{{1,9}}|{_WORD}) (?P<genitive>{'|'.join(_NOUNS)}) "
    rf"(?P<part>[0-9]{{1,9}}['’](?:s)?[ıiuü]|{_WORD}) eksik\. "
    rf"mevcut (?P<noun>{'|'.join(_NOUNS.values())}) sayısını "
    r"(?:yalnız|yalnızca|sadece) sayı olarak yaz\.?"
)


def _number(text, *, part=False):
    if not part and re.fullmatch(r"[0-9]{1,9}", text):
        return int(text)
    if part and re.fullmatch(r"[0-9]{1,9}['’](?:s)?[ıiuü]", text):
        return int(re.split(r"['’]", text)[0])
    words = text.split(" ")
    ones = _ONES_PART if part else _ONES
    tens = _TENS_PART if part else _TENS
    if len(words) == 1:
        if words[0] in ones:
            return ones.index(words[0])
        if words[0] in tens and words[0]:
            return 10 * tens.index(words[0])
    elif len(words) == 2 and words[0] in _TENS[1:] and words[1] in ones[1:]:
        return 10 * _TENS.index(words[0]) + ones.index(words[1])
    return None


def remaining_count(task):
    """Return exact total-minus-missing for a complete supported task, else None."""
    normalized = " ".join(task.strip().translate(str.maketrans({"İ": "i", "I": "ı"})).lower().split())
    match = _PATTERN.fullmatch(normalized)
    if match is None or _NOUNS[match["genitive"]] != match["noun"]:
        return None
    total = _number(match["total"])
    missing = _number(match["part"], part=True)
    if total is None or missing is None or missing > total:
        return None
    return total - missing
