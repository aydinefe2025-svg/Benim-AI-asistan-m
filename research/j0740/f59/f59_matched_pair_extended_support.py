"""F59 — locked-F51 ENG versus MPA1 matched extended mass support.

Reanalysis only: NO new C/GR stars, NO photon-level native likelihood,
NO original nuclear EOS Bayes factor. A 1.89–2.175 M_sun two-model
comparison is possible from F51's exploratory per-EOS entries because
ENG/MPA1 share exactly the same extended mass integration window.
The same 2.175 support is NOT established for all seven F42 candidates.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

PINNED_F51_SHA256 = "3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d"
EXPECTED = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
WINDOW = (1.89, 2.1)
EXTENDED_HI = 2.175
EXPECTED_COMMON_MASS = 0.597886832314311
EXPECTED_PAIR_MASS = 0.903910842245011


def analyze(source_bytes):
    if hashlib.sha256(source_bytes).hexdigest() != PINNED_F51_SHA256:
        raise ValueError("F59_REJECT_UNPINNED_F51_INPUT")
    src = json.loads(source_bytes)
    if (src.get("schema") != "F51_pinned_F46_F48_F38_mass_support_expansion_v1"
        or src.get("status") != "F51_NUMERICAL_MASS_SUPPORT_EXPANDED_NOT_NUCLEAR_EOS_BAYES"
        or src.get("model_kind") != "seven explicitly new, nonunique F42 causal-lift first-law cold-gas candidate EOS (NOT source nuclear EOS)"
        or src.get("direct_C_RNS_models_on_common_support") != 168
        or src.get("seven_source_nuclear_EOS_Bayes") != "NOT_RUN"
        or src.get("native_photon_XPSI_joint_refit") != "NOT_RUN"
        or src.get("global_fixed_J_rotating_stability") != "NOT_ESTABLISHED"):
        raise ValueError("F59_PHYSICS_SOURCE_SCOPE_MISMATCH")
    if tuple(src.get("common_verified_mass_window_msun", ())) != WINDOW:
        raise ValueError("F59_COMMON_WINDOW_MISMATCH")
    w = float(src["common_radio_prior_mass_fraction_now"])
    if not math.isclose(w, EXPECTED_COMMON_MASS, rel_tol=0, abs_tol=1e-12):
        raise ValueError("F59_COMMON_PRIOR_MASS_MISMATCH")
    per = src["per_eos_real_mass_support"]
    if set(per) != set(EXPECTED):
        raise ValueError("F59_SEVEN_MODEL_INVENTORY_MISMATCH")
    for model in ("ENG", "MPA1"):
        if (float(per[model]["max_m"]) != EXTENDED_HI
            or list(per[model]["direct_root_masses_exploratory_above_2p10"]) != [2.125, 2.15, 2.175]):
            raise ValueError("F59_ENG_MPA1_SUPPORT_NOT_MATCHED")
    if float(per["WFF1"]["max_m"]) != 2.1 or float(per["APR4_EPP"]["max_m"]) != 2.15:
        raise ValueError("F59_CANNOT_CLAIM_SEVEN_MODEL_EXTENDED_COMMON_WINDOW")
    surfaces = src["surfaces"]
    if len(surfaces) != 6:
        raise ValueError("F59_SIX_KDE_SURFACES_REQUIRED")
    rows = []
    wext = None
    w215 = None
    for name, surface in sorted(surfaces.items()):
        initial = surface["common_24_direct_root_observational_integrals"]
        extra = surface["per_EOS_exploratory_actual_direct_C_GR_support_scores_NOT_DIRECTLY_COMPARABLE"]
        if set(initial) != set(EXPECTED) or set(extra) != set(EXPECTED):
            raise ValueError("F59_MODEL_INVENTORY_NOT_COMPLETE")
        if set(["ENG","MPA1"]) - set(initial):
            raise ValueError("F59_MISSING_PAIR")
        if w215 is None:
            w215 = float(extra["APR4_EPP"]["mass_prior_coverage"])
        elif not math.isclose(w215, float(extra["APR4_EPP"]["mass_prior_coverage"]), abs_tol=1e-12):
            raise ValueError("F59_2P15_COVERAGE_INCONSISTENT")
        pair = {}
        for model in ("ENG", "MPA1"):
            old, new = initial[model], extra[model]
            if (old["mass_lo_msun"] != WINDOW[0] or old["mass_hi_msun"] != WINDOW[1]
                or new["mass_lo_msun"] != WINDOW[0] or new["mass_hi_msun"] != EXTENDED_HI):
                raise ValueError("F59_INCOMPARABLE_PAIR_WINDOWS")
            if (not math.isclose(float(old["mass_prior_coverage"]), w, abs_tol=1e-12)
                or not math.isclose(float(new["mass_prior_coverage"]), EXPECTED_PAIR_MASS, abs_tol=1e-12)):
                raise ValueError("F59_INCOMPARABLE_PAIR_MASS_PRIORS")
            cond = float(old["conditional_on_verified_mass_window_L_over_Z"])
            old_integral = float(old["likelihood_full_radio_prior_window_contribution"])
            new_integral = float(new["likelihood_full_radio_prior_window_contribution"])
            if not all(map(math.isfinite, (cond, old_integral, new_integral))):
                raise ValueError("F59_NONFINITE_INPUT")
            if cond < 0 or old_integral < 0 or new_integral < old_integral - 1e-9:
                raise ValueError("F59_NEGATIVE_OR_NONMONOTONE_LIKELIHOOD")
            if not math.isclose(w * cond, old_integral, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError("F59_OLD_WINDOW_CONTRIBUTION_MISMATCH")
            pair[model] = {
                "in_window_contribution_1p89_to_2p10": old_integral,
                "expanded_contribution_1p89_to_2p175": new_integral,
                "new_high_mass_slice_contribution_2p10_to_2p175": new_integral - old_integral,
            }
            wext = float(new["mass_prior_coverage"])
        gap = pair["MPA1"]["expanded_contribution_1p89_to_2p175"] - pair["ENG"]["expanded_contribution_1p89_to_2p175"]
        if gap <= 0:
            raise ValueError("F59_EXPECTED_PAIRWISE_MPA1_LEADER_NOT_REPRODUCED")
        low_lead = max(pair, key=lambda m:pair[m]["in_window_contribution_1p89_to_2p10"])
        if low_lead != surface["new_common_window_highest_score"]:
            raise ValueError("F59_F51_LEADER_NOT_REPRODUCED")
        remainder = 1-wext
        if remainder <= 0:
            raise ValueError("F59_TAIL_INVALID")
        rows.append({
            "kde":name,
            "leader_in_1p89_to_2p10":low_lead,
            "leader_in_pairwise_1p89_to_2p175":"MPA1",
            "matched_pair":pair,
            "MPA1_minus_ENG_extended_integral":gap,
            "minimum_missing_tail_mean_ENG_minus_MPA1_to_reverse":gap/remainder,
        })
    if not math.isclose(wext, EXPECTED_PAIR_MASS, abs_tol=1e-12):
        raise ValueError("F59_REMAINING_MASS_PRIOR_COVERAGE_MISMATCH")
    if not (w < w215 < wext < 1):
        raise ValueError("F59_INVALID_MASS_PARTITION")
    if sum(r["leader_in_1p89_to_2p10"] == "ENG" for r in rows) != 2:
        raise ValueError("F59_F51_PRIOR_LEADER_PATTERN_CHANGED")
    return {
        "schema":"F59_pinned_F51_pairwise_extended_mass_support_v1",
        "status":"PAIRWISE_EXPLORATORY_F42_REANALYSIS_NOT_NUCLEAR_EOS_BAYES",
        "F51_sha256":PINNED_F51_SHA256,
        "prior_mass_fractions":{
            "1p89_to_2p10":w,
            "2p10_to_2p15":w215-w,
            "2p15_to_2p175":wext-w215,
            "outside_1p89_to_2p175":1-wext,
        },
        "pairwise_extended_winner_count":{"MPA1":len(rows),"ENG":0},
        "rank_reversals_relative_to_short_window":2,
        "six_surface_details":rows,
        "nonclaims":[
            "No simultaneous 2.175 M_sun seven-model support: APR4_EPP ends 2.15; WFF1 ends 2.10",
            "No source-native nuclear-EOS physical admissibility, turning-point stability, photon-level likelihood or Bayes factor established",
            "The 9.61% remaining prior mass is a diagnostic complement, not an empirical upper bound on remaining likelihood",
            "Exploratory F51 Simpson/trapezoid/integration resolution error is not guaranteed negligible",
            "The required tail mean is a hypothetical reversal condition, not a tail estimate",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--f51", default="research/j0740/f51/F51_results.json")
    p.add_argument("--out", default="results/F59/F59_matched_pair_extended_support.json")
    a = p.parse_args()
    result = analyze(Path(a.f51).read_bytes())
    target = Path(a.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("F59: MPA1 6/6 under pairwise matching, 2 flips, no global EOS claim",flush=True)


if __name__ == "__main__":
    main()
