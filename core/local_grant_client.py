"""One-task HTTPS client: verified TLS, no redirects, no automatic retries.

The origin is selected by the operator, never by a downloaded ticket.
The grant is supplied in the Authorization header, never in a URL.
"""
import re
import ssl
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from core.local_task_handoff import MAX_FILE_BYTES, encode_file, parse_file, validate_ticket

_GRANT = re.compile(r"[0-9a-f]{32}\.[0-9a-f]{64}")

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalGrantClient:
    def __init__(self, origin, *, ca_file=None):
        u = urlsplit(origin)
        if (u.scheme != "https" or not u.hostname or u.username is not None
                or u.password is not None or u.path not in ("","/")
                or u.query or u.fragment or any(c.isspace() for c in origin)):
            raise ValueError("Use a trusted HTTPS origin without path or credentials")
        self.origin = "https://" + u.netloc
        context = ssl.create_default_context(cafile=ca_file)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context), _NoRedirect())

    def _post(self, path, grant, data=None):
        if not isinstance(grant,str) or not _GRANT.fullmatch(grant):
            raise PermissionError("Invalid grant")
        req=urllib.request.Request(self.origin+path,
            data=b"" if data is None else encode_file(data), method="POST",
            headers={"Authorization":"Bearer "+grant,
                     "Content-Type":"application/json","Accept":"application/json"})
        try:
            with self._opener.open(req,timeout=20) as response:
                raw=response.read(MAX_FILE_BYTES+1)
                if response.status != 200:
                    raise RuntimeError("Unexpected status")
                return parse_file(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise PermissionError("Grant denied or consumed") from None
            raise RuntimeError("Request failed; reconcile before any retry") from None
        except (OSError,ValueError):
            raise RuntimeError("Network or result uncertain; do not repeat inference") from None

    def take(self, grant):
        return validate_ticket(self._post("/v1/local-task/take",grant))

    def finish(self, grant, result):
        receipt = self._post("/v1/local-task/finish",grant,result)
        if (not isinstance(receipt,dict) or receipt.get("id") != result.get("job_id")
                or receipt.get("status") != "review_pending"
                or receipt.get("readback") is not True or receipt.get("verified") is not False):
            raise RuntimeError("Receipt uncertain; do not repeat inference")
        return receipt
