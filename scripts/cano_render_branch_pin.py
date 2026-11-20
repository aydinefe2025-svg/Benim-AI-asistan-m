"""One-time, fail-closed Render source-branch correction for CANO.

This does NOT deploy code. It only links the existing Render service to the
production branch if that branch and the latest LIVE deploy match the known
reviewed release. The API credential must be supplied at runtime, never stored
in source code or emitted in logs. No Neon job, auto-deploy or code PR is touched.
"""
from __future__ import annotations

import json
import os
import re
from urllib.request import Request, urlopen

REPO = "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m"
SERVICE_ID = "srv-dbiulm8473hc73amkjtg"
TARGET_BRANCH = "cano-production"
EXPECTED_LIVE_SHA = "db932611dafa599a6c76392abe53e6c4623d4ca1"

_SHA = re.compile(r"[a-f0-9]{40}\Z")
_API = "https://api.render.com/v1/services/" + SERVICE_ID
_GITHUB_REF = ("https://api.github.com/repos/aydinefe2025-svg/"
               "Benim-AI-asistan-m/git/ref/heads/" + TARGET_BRANCH)


class VerificationBlocked(Exception):
    """An external fact cannot be proved; make no further changes."""


def plan_branch_pin(service, latest_deploy, production_sha):
    """Pure, strict policy: only repoint the existing service to its live code.

    Return (allowed, limited_reason). No network, secrets or side effects.
    """
    if not isinstance(service, dict) or not isinstance(latest_deploy, dict):
        return False, "missing_evidence"
    if (service.get("id") != SERVICE_ID or service.get("repo") != REPO):
        return False, "wrong_service"
    if (service.get("autoDeploy") != "no"
            or service.get("autoDeployTrigger") != "off"):
        return False, "autodeploy_not_disabled"
    if latest_deploy.get("status") != "live":
        return False, "deployment_not_live"
    commit = latest_deploy.get("commit")
    live_sha = commit.get("id") if isinstance(commit, dict) else None
    if (not isinstance(production_sha, str)
            or not _SHA.fullmatch(production_sha)
            or production_sha != EXPECTED_LIVE_SHA
            or live_sha != EXPECTED_LIVE_SHA):
        return False, "release_sha_mismatch"
    branch = service.get("branch")
    if branch == TARGET_BRANCH:
        return True, "already_pinned"
    if branch == "main":
        return True, "pin_required"
    return False, "unrecognized_source_branch"


def _read_json(url, *, token=None, method="GET", body=None):
    headers = {
        "Accept": "application/json",
        "User-Agent": "cano-render-pin/1.0",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read(500_000).decode("utf-8"))


def _production_sha():
    result = _read_json(_GITHUB_REF)
    obj = result.get("object") if isinstance(result, dict) else None
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise VerificationBlocked("invalid_production_ref")
    return sha


def _service(token):
    result = _read_json(_API, token=token)
    if isinstance(result, dict) and isinstance(result.get("service"), dict):
        result = result["service"]
    if not isinstance(result, dict):
        raise VerificationBlocked("invalid_service")
    return result


def _latest_deploy(token):
    result = _read_json(_API + "/deploys?limit=1", token=token)
    if not isinstance(result, list) or not result:
        raise VerificationBlocked("missing_deploy")
    item = result[0]
    if isinstance(item, dict) and isinstance(item.get("deploy"), dict):
        item = item["deploy"]
    if not isinstance(item, dict):
        raise VerificationBlocked("invalid_deploy")
    return item


def pin_service_branch(token):
    """Require two GitHub reads and fresh Render proof before a single PATCH.

    An already configured service is idempotent. PATCH changes *only* branch;
    autodeploy must already be off. Re-read actual service and latest deploy.
    """
    if not isinstance(token, str) or not token.strip():
        raise VerificationBlocked("missing_api_key")
    sha_before = _production_sha()
    current = _service(token)
    live = _latest_deploy(token)
    sha_after = _production_sha()
    if sha_before != sha_after:
        raise VerificationBlocked("production_ref_moved")
    allowed, reason = plan_branch_pin(current, live, sha_after)
    if not allowed:
        raise VerificationBlocked(reason)
    if reason == "pin_required":
        # Never send an enabled auto-deploy setting or a code commit here.
        _read_json(_API, token=token, method="PATCH",
                   body={"branch": TARGET_BRANCH})
    after = _service(token)
    newer_live = _latest_deploy(token)
    allowed, check = plan_branch_pin(after, newer_live, _production_sha())
    if not allowed or check != "already_pinned":
        raise VerificationBlocked("readback_not_pinned")
    return "pinned_and_verified" if reason == "pin_required" else "already_pinned"


def main():
    if os.getenv("CANO_RENDER_PIN_ENABLED") != "true":
        print("CANO_RENDER_PIN_RESULT=disabled")
        return 1
    try:
        result = pin_service_branch(os.getenv("RENDER_API_KEY", ""))
    except VerificationBlocked as exc:
        # Safe enumerated reasons, never exception details or credentials.
        print("CANO_RENDER_PIN_RESULT=" + str(exc))
        return 1
    except Exception:
        print("CANO_RENDER_PIN_RESULT=external_verification_failed")
        return 1
    print("CANO_RENDER_PIN_RESULT=" + result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
