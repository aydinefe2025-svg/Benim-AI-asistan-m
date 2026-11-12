"""Install pinned official PGDG Debian 12 PostgreSQL 18 client without sudo.

Operator-only Render build step; downloading signed-source artifacts alone is
not a backup. We additionally pin exact SHA256 of each artifact.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile
import urllib.parse
import urllib.request

BASE = "https://apt.postgresql.org/pub/repos/apt/pool/main/p/postgresql-18/"
DEBS = {
    "postgresql-client-18_18.6-3.pgdg12+1_amd64.deb": (
        2_134_408,
        "b06092bdf3f19a0991fa4a002055bbad680b827871968e6863ea1c71273063cd",
    ),
    "libpq5_18.6-3.pgdg12+1_amd64.deb": (
        265_240,
        "af24a85e9d856c6339b55251d059cd52c23dbda103f5caf6a4050c512573d102",
    ),
}


def fetch_verified(name: str, expected_bytes: int, expected_sha: str) -> bytes:
    if name not in DEBS or DEBS[name] != (expected_bytes, expected_sha):
        raise RuntimeError("unapproved PostgreSQL artifact")
    url = BASE + urllib.parse.quote(name)
    with urllib.request.urlopen(url, timeout=35) as response:
        if urllib.parse.urlsplit(response.geturl()).hostname != "apt.postgresql.org":
            raise RuntimeError("PostgreSQL artifact unexpected redirect")
        blob = response.read(expected_bytes + 1)
    if len(blob) != expected_bytes or hashlib.sha256(blob).hexdigest() != expected_sha:
        raise RuntimeError("PostgreSQL artifact checksum mismatch")
    return blob


def install(project_root: Path) -> dict:
    if platform.system() != "Linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("PG18 artifact only verified on Linux amd64")
    project_root = Path(project_root).resolve()
    target = project_root / ".cano-pg18"
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    for filename, (count, sha) in DEBS.items():
        blob = fetch_verified(filename, count, sha)
        with tempfile.NamedTemporaryFile(dir=target, suffix=".deb", delete=False) as fh:
            fh.write(blob)
            tempname = fh.name
        try:
            subprocess.run(["dpkg-deb", "--extract", tempname, str(target)],
                           check=True, timeout=45, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            os.unlink(tempname)
    libdir = target / "usr" / "lib" / "x86_64-linux-gnu"
    binary = target / "usr" / "lib" / "postgresql" / "18" / "bin" / "pg_dump"
    if not binary.is_file() or not (libdir / "libpq.so.5").exists():
        raise RuntimeError("PGDG archive contents incomplete")
    wrapper = target / "pg_dump18"
    shell = "#!/bin/sh\nexport LD_LIBRARY_PATH=" + shlex.quote(str(libdir)) + "\nexec " + shlex.quote(str(binary)) + ' "$@"\n'
    wrapper.write_text(shell, encoding="ascii")
    wrapper.chmod(0o700)
    probe = subprocess.run([str(wrapper), "--version"], capture_output=True,
                           timeout=12, check=False, env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")})
    if probe.returncode or not re.fullmatch(rb"pg_dump \(PostgreSQL\) 18(?:\.[0-9]+)?(?: \([^\r\n]{1,70}\))?\r?\n?", probe.stdout):
        raise RuntimeError("PG18 client startup validation failed")
    return {"pg_dump18": str(wrapper), "sha_pinned": True, "client_major": 18}


if __name__ == "__main__":
    path = Path(__file__).resolve().parent.parent
    install(path)
    print("CANO official pinned PostgreSQL 18 pg_dump client ready")