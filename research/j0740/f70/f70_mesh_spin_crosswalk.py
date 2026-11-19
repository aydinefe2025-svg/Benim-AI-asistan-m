"""F70: source-locked crosswalk of F68 RNS mesh/frequency and F69 static TOV.

Diagnoses identifiability of mesh-only effects; does not solve another star,
replace an EOS, infer a physical crust, or claim a new seven-EOS Bayes factor.
Python standard library only. Inputs: original archived F68 summary, F69 star JSON.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

F68_SHA = "de2168c281ed90c975c5d658eb395cd88b3114c10e97d0137f181af61ab6f1be"
F69_SHA = "4ffe44817f978b05f9888738ac4373cf345b959cac2c27cedebd93aa8dc7fb37"
SOURCE_F67 = "d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22"
RNS_EOS_SHA = "5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16"
MASS_KEYS = ("2.073", "2.175", "2.200", "2.250")
FREQUENCY_HZ = 346.536369
STRICT_EQUAL_F_TOL_HZ = 0.005


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crosswalk(a, b):
    """Fail closed if provenance, physics scope, mass matching, or values drift."""
    if a.get("model") != "MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL":
        raise ValueError("F70_F68_MODEL_IDENTITY_DRIFT")
    if b.get("model_label") != "MPA1_PCHIP_COLD_FE56_SURFACE_V1_CONDITIONAL_NOT_ORIGINAL":
        raise ValueError("F70_F69_MODEL_IDENTITY_DRIFT")
    if (a.get("parent_F67_thermo_table_SHA256") != SOURCE_F67 or
        b.get("parent_F67_source_SHA256") != SOURCE_F67 or
        a.get("exact_identical_rns_derived_EOS_table_sha256") != RNS_EOS_SHA):
        raise ValueError("F70_PARENT_OR_RNS_EOS_IDENTITY_DRIFT")
    if a.get("seven_original_EOS_Bayes") != "NOT_RUN" or b.get("seven_original_EOS_Bayes") != "NOT_RUN":
        raise ValueError("F70_FALSE_FULL_EOS_BAYES_STATUS")
    if a.get("alternative_model_physically_certified") != "NOT_ESTABLISHED" or b.get("whole_original_seven_EOS_physically_accepted") != "NOT_ESTABLISHED":
        raise ValueError("F70_FALSE_PHYSICAL_ACCEPTANCE")
    rows = a.get("results", [])
    if len(rows) != 4 or tuple(f"{x['mass_msun']:.3f}" for x in rows) != MASS_KEYS:
        raise ValueError("F70_MASS_KEYS_OR_ROWS_CHANGED")
    if set(b.get("target_static_GR", {})) != set(MASS_KEYS):
        raise ValueError("F70_F69_STATIC_MASS_SET_DRIFT")
    shell_max = b.get("maximum_first_order_missing_shell_radius_m")
    if not isinstance(shell_max, (int, float)) or not math.isfinite(shell_max) or shell_max <= 0 or shell_max >= 1e-6:
        raise ValueError("F70_BAD_SHELL_ESTIMATE")

    out = []
    fine_pairs = 0
    max_static_mesh = 0.0
    max_rotating_mesh = 0.0
    max_F69_vs_F68_TOV = 0.0
    max_F68_static_RNS_vs_F69_TOV = 0.0
    for row, mk in zip(rows, MASS_KEYS):
        actual_f69 = b["target_static_GR"][mk]["rm"]
        if abs(actual_f69["M_msun_to_match"] - row["mass_msun"]) > 3e-7:
            raise ValueError("F70_TARGET_MG_MISMATCH")
        f69_tov = actual_f69["R_km_to_match"]
        old_tov = row["independent_static_TOV_R_km"]
        new_minus_old_tov_m = 1000 * (f69_tov - old_tov)
        static_crosscode_m = 1000 * (row["grid151x301_stat_R_km"] - f69_tov)
        if not all(math.isfinite(x) for x in (f69_tov, old_tov, new_minus_old_tov_m, static_crosscode_m)):
            raise ValueError("F70_NONFINITE_R")
        if abs(new_minus_old_tov_m) > 0.001:
            raise ValueError("F70_TOO_LARGE_CROSS_MODEL_TOV_DIFFERENCE_M")
        max_F69_vs_F68_TOV = max(max_F69_vs_F68_TOV, abs(new_minus_old_tov_m))
        max_F68_static_RNS_vs_F69_TOV = max(max_F68_static_RNS_vs_F69_TOV, abs(static_crosscode_m))
        course_f = row["grid151x301_spinning_hz"]
        if not math.isfinite(course_f) or abs(course_f - FREQUENCY_HZ) > .25:
            raise ValueError("F70_COARSE_SPIN_OUTSIDE_OLD_ACCEPTANCE")
        datum = {
            "mass_msun": float(mk), "f68_coarse_rotating_f_hz": course_f,
            "f68_coarse_f_minus_requested_hz": course_f - FREQUENCY_HZ,
            "f69_static_TOV_R_km_to_match": f69_tov,
            "f69_minus_f68_independent_static_TOV_R_m": new_minus_old_tov_m,
            "f68_coarse_static_RNS_minus_f69_static_TOV_R_m": static_crosscode_m,
            "fine_spacetime_grid_available": "grid201x401_spinning_hz" in row,
        }
        if datum["fine_spacetime_grid_available"]:
            fine_pairs += 1
            fine_f = row["grid201x401_spinning_hz"]
            delta_f = fine_f - course_f
            delta_rot = 1000 * (row["grid201x401_rot_R_eq_km"] - row["grid151x301_rot_R_eq_km"])
            delta_stat = 1000 * (row["grid201x401_stat_R_km"] - row["grid151x301_stat_R_km"])
            if not all(math.isfinite(q) for q in (fine_f, delta_f, delta_rot, delta_stat)):
                raise ValueError("F70_NONFINITE_FINE_INPUT")
            if abs(fine_f - FREQUENCY_HZ) > .25:
                raise ValueError("F70_FINE_SPIN_OUTSIDE_OLD_ACCEPTANCE")
            max_static_mesh = max(max_static_mesh, abs(delta_stat))
            max_rotating_mesh = max(max_rotating_mesh, abs(delta_rot))
            datum.update({
                "f68_fine_rotating_f_hz": fine_f,
                "fine_minus_coarse_frequency_hz": delta_f,
                "fine_minus_coarse_rotating_radius_m_not_pure_mesh": delta_rot,
                "fine_minus_coarse_static_radius_m_at_zero_spin": delta_stat,
                "same_realized_rotation_frequency_within_0p005Hz": abs(delta_f) <= STRICT_EQUAL_F_TOL_HZ,
            })
        out.append(datum)
    if fine_pairs != 2:
        raise ValueError("F70_EXPECTED_ONLY_TWO_FINE_MASS_POINTS")
    observed = {f"{x['mass_msun']:.3f}": x for x in out}
    if abs(observed["2.250"]["fine_minus_coarse_frequency_hz"]) <= STRICT_EQUAL_F_TOL_HZ:
        raise ValueError("F70_SPIN_MISMATCH_WAS_INCORRECTLY_DISMISSED")
    if max_static_mesh <= 3.0 or max_rotating_mesh <= 1.0:
        raise ValueError("F70_GRID_DIFFERENCES_MUST_BE_REPRODUCED")
    # The absolute grid/spin split cannot be inferred without a same-f root;
    # the static grid pair (f=0 in both) separately establishes a numerical difference.
    return {
        "schema": "F70_SOURCE_LOCKED_SPIN_MESH_F69_TOV_CROSSWALK_V1",
        "status": "MEASURED_SPIN_MESH_CONFOUND_F68_NOT_GRID_ONLY_CORRECTED_INTERPRETATION",
        "scientific_question": "Can F68 two-grid rotating radius delta be interpreted as pure spatial-mesh convergence?",
        "answer": "NO_FOR_2p250_Msun_WITHOUT_MATCHED_ACTUAL_SPIN",
        "F68_F69_models_identical": False,
        "F69_surface_model_conditional_not_original": True,
        "F68_real_spin_target_hz": FREQUENCY_HZ,
        "strict_same_realized_f_gate_hz": STRICT_EQUAL_F_TOL_HZ,
        "number_of_mass_roots_with_two_spacetime_grids": fine_pairs,
        "number_of_mass_roots_total": len(out),
        "max_abs_static_two_grid_radius_delta_m": max_static_mesh,
        "max_abs_rotating_two_grid_radius_delta_m_NOT_MESH_ONLY": max_rotating_mesh,
        "max_abs_F69_vs_F68_independent_TOV_radius_delta_m": max_F69_vs_F68_TOV,
        "max_abs_F68_coarse_static_RNS_vs_F69_static_TOV_radius_delta_m": max_F68_static_RNS_vs_F69_TOV,
        "F69_surface_shell_first_order_max_R_m_NOT_RIGOROUS_BOUND": shell_max,
        "ratio_static_grid_delta_to_first_order_shell_estimate_NOT_ERROR_BOUND": max_static_mesh/shell_max,
        "F68_two_grid_rotating_pure_mesh_error_certified": False,
        "F68_two_grid_static_zero_spin_numeric_mesh_effect_observed": True,
        "F69_rotating_RNS_mass_or_baryon_count": "NOT_RUN",
        "new_RNS_root_at_matched_frequency": "NOT_RUN",
        "third_spacetime_grid": "NOT_RUN",
        "seven_original_EOS_Bayes": "NOT_RUN",
        "source_native_XPSI_photon_nuisance_likelihood": "NOT_RUN",
        "next_acceptance": "For identical F68 EOS bytes and matched target gravitational mass, solve two or more rotating RNS spatial grids to reported |f-f_target|<0.005 Hz, then run a third grid and test convergence; never attribute mixed f differences to spatial truncation alone.",
        "rows": out,
        "interpretive_limit": "Cross-model TOV comparison is a numerical diagnostic, not a physical Fe56 crust measurement or a rigorous radius error budget.",
    }


def run(f68_path, f69_path, output_path):
    if sha256(f68_path) != F68_SHA or sha256(f69_path) != F69_SHA:
        raise ValueError("F70_EXACT_SOURCE_FILE_SHA_MISMATCH")
    a = json.loads(Path(f68_path).read_text(encoding="utf-8"))
    b = json.loads(Path(f69_path).read_text(encoding="utf-8"))
    result = crosswalk(a,b)
    result["F68_summary_source_sha256"] = F68_SHA
    result["F69_local_static_source_sha256"] = F69_SHA
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n", encoding="utf-8", newline="\n")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--f68", required=True, type=Path)
    p.add_argument("--f69", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    ans = run(args.f68, args.f69, args.out)
    print(json.dumps({"status":ans["status"], "max_static_grid_delta_m":ans["max_abs_static_two_grid_radius_delta_m"],
                     "mass_2p250_delta_spin_hz":ans["rows"][-1]["fine_minus_coarse_frequency_hz"],
                     "max_F69_TOV_crosswalk_m":ans["max_abs_F69_vs_F68_independent_TOV_radius_delta_m"]},sort_keys=True))


if __name__ == "__main__":
    main()
