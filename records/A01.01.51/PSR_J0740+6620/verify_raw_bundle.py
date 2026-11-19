from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1] / ".j0740_bundle_verify_tmp"
bundle = root / "j0740_raw_inputs_bundle.tar.gz"
expected_bundle_size = 222_910_037
expected_bundle_md5 = "9fec0d9cd29df816bfea78565d0a6bb2"
expected_bundle_sha256 = "5057752bec77b2417368fe144a6c1fc94203ce1eb15b975613a9ca334ddbfc2f"
expected_sources = {
    "mr_samples_and_contours.tar.gz": (40_605_003, "ca8e70eeca81feb71321f1a88a24f2f9"),
    "NICER_XMM_J0740_full_original_weighted.txt": (168_073_694, "c28a3995e60f364b34a66c29a37bf79d"),
    "LCEHL_EOS_posterior_samples_PSR_GW_NICER.h5": (192_213_112, "64bdad9b43726162a25546d07305747d"),
}

parts = sorted(root.glob("part-*"))
assert len(parts) == 54, f"expected 54 parts, found {len(parts)}"
assert [p.name for p in parts] == [f"part-{i:03d}" for i in range(54)], "part sequence has gaps"
assert sum(p.stat().st_size for p in parts) == expected_bundle_size, "part byte total mismatch"

md5 = hashlib.md5()
sha256 = hashlib.sha256()
with bundle.open("wb") as target:
    for part in parts:
        with part.open("rb") as source:
            while block := source.read(8 * 1024 * 1024):
                md5.update(block)
                sha256.update(block)
                target.write(block)

assert bundle.stat().st_size == expected_bundle_size
assert md5.hexdigest() == expected_bundle_md5, md5.hexdigest()
assert sha256.hexdigest() == expected_bundle_sha256, sha256.hexdigest()

source_dir = root / "raw_inputs"
source_dir.mkdir(exist_ok=True)
with tarfile.open(bundle, "r:gz") as archive:
    archive.extractall(source_dir, filter="data")

checks = {}
for basename, (expected_size, expected_md5) in expected_sources.items():
    matches = list(source_dir.rglob(basename))
    assert len(matches) == 1, f"expected one {basename}, found {len(matches)}"
    path = matches[0]
    file_md5 = hashlib.md5()
    file_sha256 = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(8 * 1024 * 1024):
            file_md5.update(block)
            file_sha256.update(block)
    assert path.stat().st_size == expected_size, (basename, path.stat().st_size)
    assert file_md5.hexdigest() == expected_md5, (basename, file_md5.hexdigest())
    checks[basename] = {
        "bytes": path.stat().st_size,
        "md5": file_md5.hexdigest(),
        "sha256": file_sha256.hexdigest(),
        "path": str(path),
    }

out = {
    "status": "PASS",
    "parts": len(parts),
    "bytes": bundle.stat().st_size,
    "bundle_md5": md5.hexdigest(),
    "bundle_sha256": sha256.hexdigest(),
    "sources": checks,
}
result_path = Path(__file__).with_name("raw_bundle_verification.json")
result_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2))
