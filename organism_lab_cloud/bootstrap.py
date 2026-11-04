"""Build an ephemeral Streamlit OIDC secrets file from Render secrets."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def write_oidc_file(env=None, directory=None):
    env = os.environ if env is None else env
    required = {
        "redirect_uri": "LAB_OIDC_REDIRECT_URI",
        "cookie_secret": "LAB_OIDC_COOKIE_SECRET",
        "client_id": "LAB_OIDC_CLIENT_ID",
        "client_secret": "LAB_OIDC_CLIENT_SECRET",
        "server_metadata_url": "LAB_OIDC_METADATA_URL",
    }
    values = {key: env.get(name, "").strip() for key, name in required.items()}
    if not all(values.values()) or len(values["cookie_secret"].encode("utf-8")) < 32:
        env.pop("ORGANISM_LAB_OIDC_CONFIGURED", None)
        return None
    target_dir = Path(directory or tempfile.gettempdir()) / "organism-lab-runtime"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "secrets.toml"
    body = "[auth]\n" + "".join(f"{key} = {json.dumps(value, ensure_ascii=False)}\n"
                                 for key, value in values.items())
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
        output.write(body)
    env["STREAMLIT_SECRETS_FILES"] = json.dumps([str(path)])
    env["ORGANISM_LAB_OIDC_CONFIGURED"] = "1"
    return path


def main():
    write_oidc_file()
    dashboard = Path(__file__).resolve().parent / "organism_lab" / "dashboard.py"
    port = os.environ.get("PORT", "8501")
    command = [sys.executable, "-m", "streamlit", "run", str(dashboard),
               "--server.address", "0.0.0.0", "--server.port", port,
               "--server.headless", "true"]
    raise SystemExit(subprocess.call(command))


if __name__ == "__main__":
    main()

