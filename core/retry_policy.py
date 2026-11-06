"""Bounded retries for transient network/provider errors, without logging secrets."""
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from urllib.error import HTTPError, URLError

_MAX_RETRY_DELAY = 60.0


def is_transient(error):
    status = getattr(error, 'status_code', getattr(error, 'code', None))
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(error, (TimeoutError, ConnectionError, URLError)) or type(error).__name__ in {
        'APITimeoutError', 'APIConnectionError', 'ReadTimeout', 'ConnectTimeout'}


def _retry_after(error):
    """Read a provider retry hint, capped so a bad header cannot stall a task."""
    response = getattr(error, 'response', None)
    headers = getattr(error, 'headers', None) or getattr(response, 'headers', None)
    if headers is None:
        return None
    for name in ('Retry-After', 'x-ratelimit-reset-tokens'):
        try:
            value = headers.get(name)
        except (AttributeError, TypeError):
            value = None
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        try:
            seconds = float(value)
        except ValueError:
            try:
                reset_at = parsedate_to_datetime(value)
                if reset_at.tzinfo is None:
                    reset_at = reset_at.replace(tzinfo=timezone.utc)
                seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                match = re.fullmatch(r'(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?', value)
                if not match or not any(match.groups()):
                    continue
                seconds = float(match.group(1) or 0) * 60 + float(match.group(2) or 0)
        if seconds >= 0:
            return min(seconds, _MAX_RETRY_DELAY)
    return None


def retry_transient(operation, *, attempts=3, sleep=time.sleep):
    if not 1 <= attempts <= 3:
        raise ValueError('At most three attempts are allowed')
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            if attempt + 1 == attempts or not is_transient(error):
                raise
            sleep(_retry_after(error) or min(2 ** attempt, 4))

