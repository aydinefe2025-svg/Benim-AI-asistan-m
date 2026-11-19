from __future__ import annotations

import contextlib
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
TMP = HERE.parent / ".j0740_bundle_verify_tmp"
DATA = TMP / "raw_inputs"
FLOW = TMP / "jester_flow" / "J0740_amsterdam_gamma"
RUNTIME = HERE.parent / ".j0740_runtime_cp312"
SOURCE = TMP / "historical_source.py"
OUTPUT = DATA / "J0740_final_weighted_old_source_update.json"
DELIVERABLE = HERE / "J0740_final_weighted_old_source_update.json"
LOG = HERE / "J0740_local_reproduction.log"
MANIFEST = HERE / "J0740_local_reproduction_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(8 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


source_bytes = SOURCE.read_bytes().replace(b"\r\n", b"\n")
source = source_bytes.decode("utf-8")
source_sha = hashlib.sha256(source_bytes).hexdigest()
git_blob_sha = hashlib.sha1(
    b"blob " + str(len(source_bytes)).encode() + b"\0" + source_bytes
).hexdigest()
assert git_blob_sha == "9fa9db8b95107c291688117cda6d41a470e6775e", git_blob_sha

patches = {
    "sys.path.insert(0,'/workspace/archive/jester_flow/J0740_amsterdam_gamma')":
        f"sys.path.insert(0,r'{FLOW}')",
    "base='/workspace/archive'": f"base=r'{DATA}'",
    "Flow.from_directory('/workspace/archive/jester_flow/J0740_amsterdam_gamma')":
        f"Flow.from_directory(r'{FLOW}')",
}
adapted = source
for old, new in patches.items():
    assert adapted.count(old) == 1, f"path adaptation point not unique: {old}"
    adapted = adapted.replace(old, new)
adapted_sha = hashlib.sha256(adapted.encode("utf-8")).hexdigest()

sys.path.insert(0, str(RUNTIME))
os.environ["JAX_PLATFORMS"] = "cpu"
started = time.time()
run_error = None
with LOG.open("w", encoding="utf-8") as log:
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            exec(compile(adapted, str(SOURCE), "exec"), {"__file__": str(SOURCE), "__name__": "__main__"})
    except BaseException as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        log.write("\nRUN_ERROR: " + run_error + "\n")

elapsed = time.time() - started
manifest = {
    "status": "FAILED" if run_error else "PASS",
    "started_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(),
    "elapsed_seconds": elapsed,
    "python": sys.version,
    "platform": platform.platform(),
    "device": "JAX CPU",
    "historical_script": "research/j0740/historical_20261025/run_final_weighted_old_source_update.py",
    "historical_script_git_blob_sha1": git_blob_sha,
    "historical_script_sha256": source_sha,
    "runtime_path_adapter_sha256": adapted_sha,
    "path_only_adaptations": 3,
    "bundle_verification": str(HERE / "raw_bundle_verification.json"),
    "flow_assets_sha256": {p.name: sha256(p) for p in sorted(FLOW.iterdir()) if p.is_file()},
    "log": str(LOG),
}
if run_error is None and OUTPUT.exists():
    result = json.loads(OUTPUT.read_text(encoding="utf-8"))
    DELIVERABLE.write_bytes(OUTPUT.read_bytes())
    metrics = result["metrics"]
    kde = metrics["KDE_new_bw=0.16|KDE_old_bw=0.16|offset=0.0"]
    flow = metrics["FLOW_new|KDE_old_bw=0.16|offset=0.0"]
    manifest["recomputed"] = {
        "EOS_count": result["EOS_count"],
        "old_raw_samples": result["old_raw_samples"],
        "new_samples": result["new_samples"],
        "old_corrected_weight_ESS": result["old_prior_corrected_weight_ESS"],
        "KDE_KDE_bw016": kde,
        "Flow_KDE_bw016": flow,
    }
    manifest["result_output"] = str(DELIVERABLE)
    manifest["result_sha256"] = sha256(DELIVERABLE)
    manifest["independent_method_agreement"] = {
        "R14_median_abs_diff_km": abs(kde["R14_km"][1] - flow["R14_km"][1]),
        "Lambda14_median_abs_diff": abs(kde["Lambda14"][1] - flow["Lambda14"][1]),
        "R2073_median_abs_diff_km": abs(kde["R_at_2.073_km"][1] - flow["R_at_2.073_km"][1]),
        "Mmax_median_abs_diff_Msun": abs(kde["Mmax_Msun"][1] - flow["Mmax_Msun"][1]),
    }
else:
    manifest["status"] = "FAILED"
    manifest["result_output_exists"] = OUTPUT.exists()
    manifest["run_error"] = run_error

MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
if run_error:
    raise RuntimeError(run_error)
