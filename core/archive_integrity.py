"""Detect accidental JSON archive changes; a digest is not authentication."""
import hashlib
import json
import hmac


def archive_digest(payload):
    content = {key: value for key, value in payload.items() if key != 'integrity'}
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                     allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def check_archive_integrity(payload):
    # Legacy v1 downloads remain importable. They carry no integrity assurance.
    if 'integrity' not in payload:
        return
    receipt = payload['integrity']
    if not isinstance(receipt, dict) or receipt.get('algorithm') != 'sha256':
        raise ValueError('Invalid integrity receipt')
    expected = receipt.get('digest')
    if (not isinstance(expected, str) or len(expected) != 64 or
            any(char not in '0123456789abcdef' for char in expected)):
        raise ValueError('Invalid archive digest')
    if not hmac.compare_digest(expected, archive_digest(payload)):
        raise ValueError('Archive integrity check failed')
