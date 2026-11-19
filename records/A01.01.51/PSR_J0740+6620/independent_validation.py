from __future__ import annotations

import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TMP = HERE.parent / ".j0740_bundle_verify_tmp"
current = json.loads((HERE / "J0740_final_weighted_old_source_update.json").read_text(encoding="utf-8"))
historical_bytes = (TMP / "historical_result.json").read_bytes()
historical_blob = hashlib.sha1(
    b"blob " + str(len(historical_bytes)).encode() + b"\0" + historical_bytes
).hexdigest()
assert historical_blob == "814735349463152169a9c28e8c5511d58f637d7a", historical_blob
historical = json.loads(historical_bytes)
historical_full_bytes = (TMP / "historical_full_result.json").read_bytes()
historical_full_blob = hashlib.sha1(
    b"blob " + str(len(historical_full_bytes)).encode() + b"\0" + historical_full_bytes
).hexdigest()
assert historical_full_blob == "7d0ee5dc897f5292376f1448abdf70f64bf5a1a2", historical_full_blob
historical_full = json.loads(historical_full_bytes)
bundle = json.loads((HERE / "raw_bundle_verification.json").read_text(encoding="utf-8"))
run_manifest = json.loads((HERE / "J0740_local_reproduction_manifest.json").read_text(encoding="utf-8"))

kde = current["metrics"]["KDE_new_bw=0.16|KDE_old_bw=0.16|offset=0.0"]
flow = current["metrics"]["FLOW_new|KDE_old_bw=0.16|offset=0.0"]
reference = historical_full["metrics"]["KDE_new_bw=0.16|KDE_old_bw=0.16|offset=0.0"]
flow_reference = historical_full["metrics"]["FLOW_new|KDE_old_bw=0.16|offset=0.0"]
comparisons = {
    "R14_km": {"q16": (kde["R14_km"][0], reference["R14_km"][0]), "median": (kde["R14_km"][1], reference["R14_km"][1]), "q84": (kde["R14_km"][2], reference["R14_km"][2])},
    "Lambda14": {"q16": (kde["Lambda14"][0], reference["Lambda14"][0]), "median": (kde["Lambda14"][1], reference["Lambda14"][1]), "q84": (kde["Lambda14"][2], reference["Lambda14"][2])},
    "R_at_2.073_Msun_km": {"q16": (kde["R_at_2.073_km"][0], reference["R_at_2.073_km"][0]), "median": (kde["R_at_2.073_km"][1], reference["R_at_2.073_km"][1]), "q84": (kde["R_at_2.073_km"][2], reference["R_at_2.073_km"][2])},
    "Mmax_Msun": {"q16": (kde["Mmax_Msun"][0], reference["Mmax_Msun"][0]), "median": (kde["Mmax_Msun"][1], reference["Mmax_Msun"][1]), "q84": (kde["Mmax_Msun"][2], reference["Mmax_Msun"][2])},
}
absolute_differences = {
    metric: {quantile: abs(actual - expected) for quantile, (actual, expected) in values.items()}
    for metric, values in comparisons.items()
}
assert max(diff for q in absolute_differences.values() for diff in q.values()) < 1e-8
assert abs(kde["ESS"] - reference["ESS"]) < 1e-8
assert current["EOS_count"] == historical_full["EOS_count"] == historical["primary_kde_kde"]["n_EOS"] == 10_000
assert current["old_raw_samples"] == historical_full["old_raw_samples"] == historical["old_source_prior_correction"]["n_samples"] == 1_600_920
assert current["new_samples"] == 379_669
assert bundle["sources"]["mr_samples_and_contours.tar.gz"]["md5"] == historical["data_checksums"]["Salmi_2024_MR_archive_md5"]
assert bundle["sources"]["NICER_XMM_J0740_full_original_weighted.txt"]["md5"] == historical["data_checksums"]["Miller_2021_original_weighted_source_md5"]
assert bundle["sources"]["LCEHL_EOS_posterior_samples_PSR_GW_NICER.h5"]["md5"] == historical["data_checksums"]["Legred_PSR_GW_NICER_H5_md5"]

flow_differences = {
    "R14_km_median": abs(flow["R14_km"][1] - flow_reference["R14_km"][1]),
    "Lambda14_median": abs(flow["Lambda14"][1] - flow_reference["Lambda14"][1]),
    "R_at_2.073_Msun_km_median": abs(flow["R_at_2.073_km"][1] - flow_reference["R_at_2.073_km"][1]),
    "Mmax_Msun_median": abs(flow["Mmax_Msun"][1] - flow_reference["Mmax_Msun"][1]),
}
assert max(flow_differences.values()) < 1e-5

out = {
    "status": "PASS",
    "historical_result_path": "research/j0740/historical_20261025/J0740_EOS_FINAL_RESULT.json",
    "historical_result_git_blob_sha1": historical_blob,
    "historical_result_sha256": hashlib.sha256(historical_bytes).hexdigest(),
    "historical_full_result_git_blob_sha1": historical_full_blob,
    "historical_full_result_sha256": hashlib.sha256(historical_full_bytes).hexdigest(),
    "recomputed_result_sha256": run_manifest["result_sha256"],
    "source_input_md5s_match_historical_manifest": True,
    "sample_counts_match": {"new_Salmi": current["new_samples"], "old_Miller": current["old_raw_samples"], "Legred_EOS": current["EOS_count"]},
    "KDE_to_KDE_abs_differences": absolute_differences,
    "Flow_to_KDE_abs_differences_vs_historical_flow_check": flow_differences,
    "KDE_KDE_ESS": kde["ESS"],
    "Flow_KDE_ESS": flow["ESS"],
    "likelihood_handling": "Replaced the historical J0740 factor with the Salmi 2024 source posterior ratio; no duplicate multiplication of the same NICER photon data.",
}
out_path = HERE / "J0740_independent_validation.json"
out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2))
