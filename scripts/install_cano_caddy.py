"""Install only the pinned, hash-verified official Caddy release."""
import hashlib
import io
import os
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "2.11.9"
ARTIFACTS = {
    "Linux": ("linux_amd64.tar.gz", "5b8cb7faf8726a2028ad96a66e54e6e81e8f361bc6175e5d22bbd997cc5177fb", "caddy"),
    "Windows": ("windows_amd64.zip", "ad93112d335ee687100c4c9f11bced16ca590377976b7fe7883882b9e797e472", "caddy.exe"),
}
def install(root):
    if platform.machine().lower() not in {"amd64","x86_64"} or platform.system() not in ARTIFACTS:
        raise RuntimeError("Unsupported architecture")
    suffix, expected, executable = ARTIFACTS[platform.system()]
    name = f"caddy_{VERSION}_{suffix}"
    url = f"https://github.com/caddyserver/caddy/releases/download/v{VERSION}/{name}"
    with urllib.request.urlopen(url,timeout=60) as response:
        data = response.read(24*1024*1024+1)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Caddy release hash mismatch")
    if suffix.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            binary = archive.read(executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as archive:
            item=archive.getmember(executable)
            if not item.isfile():
                raise RuntimeError("Not a regular binary")
            binary=archive.extractfile(item).read()
    root.mkdir(exist_ok=True)
    path=root/executable
    if path.is_symlink():
        raise RuntimeError("Refuse symlink")
    tmp=path.with_suffix(".new")
    with tmp.open("xb") as f:
        f.write(binary)
    tmp.chmod(0o755)
    os.replace(tmp,path)
    print("Caddy",VERSION,"official archive SHA256 verified")
    return path

if __name__=="__main__":
    install(Path(".cano-bin"))
