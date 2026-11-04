"""Bounded retries for transient network/provider errors, without logging secrets."""
import time
from urllib.error import HTTPError, URLError


def is_transient(error):
    status = getattr(error, 'status_code', getattr(error, 'code', None))
    if status is not None:
        return status in {408, 429, 500, 502, 503, 504}
    return isinstance(error, (TimeoutError, ConnectionError, URLError)) or type(error).__name__ in {
        'APITimeoutError', 'APIConnectionError', 'ReadTimeout', 'ConnectTimeout'}


def retry_transient(operation, *, attempts=3, sleep=time.sleep):
    if not 1 <= attempts <= 3:
        raise ValueError('At most three attempts are allowed')
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:
            if attempt + 1 == attempts or not is_transient(error):
                raise
            sleep(min(2 ** attempt, 4))
