"""F60 — analytic mass-prior tail partition on existing F51/F59.

Source-locked decomposition, NOT new C/GR stars, NOT EOS Bayes, NOT physical
branch existence. The separate low and high radio-prior tails resolve which
physical mass interval to prioritize for a *future* native EOS calculation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

SOURCE_SHA256 = "3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d"
MU = 2.082
SIGMA = .0703
TRUNC_Z = 5.
LOW = 1.89
COMMON_HI = 2.1
PAIR_HI = 2.175
TARGETS = (2.2, 2.225, 2.25, 2.275, 2.3)


def standard_normal_cdf(z):
    if not math.isfinite(z):
        raise ValueError("F60_NONFINITE_GAUSSIAN_ARGUMENT")
    return .5 * math.erfc(-z/math.sqrt(2))


def truncated_normal_cdf(x, mu=MU, sigma=SIGMA, zmax=TRUNC_Z):
    if not all(map(math.isfinite, (x,mu,sigma,zmax))) or sigma<=0 or zmax<=0:
        raise ValueError("F60_INVALID_RADIO_PRIOR_PARAMETERS")
    z=(x-mu)/sigma
    if z<=-zmax: return 0.
    if z>=zmax: return 1.
    normalizer=standard_normal_cdf(zmax)-standard_normal_cdf(-zmax)
    return (standard_normal_cdf(z)-standard_normal_cdf(-zmax))/normalizer


def inspect(source_bytes):
    if hashlib.sha256(source_bytes).hexdigest()!=SOURCE_SHA256:
        raise ValueError("F60_ORIGINAL_F51_SHA_DRIFT")
    src=json.loads(source_bytes)
    if (src.get("schema")!="F51_pinned_F46_F48_F38_mass_support_expansion_v1"
        or src.get("status")!="F51_NUMERICAL_MASS_SUPPORT_EXPANDED_NOT_NUCLEAR_EOS_BAYES"
        or src.get("direct_C_RNS_models_on_common_support")!=168
        or src.get("seven_source_nuclear_EOS_Bayes")!="NOT_RUN"
        or src.get("native_photon_XPSI_joint_refit")!="NOT_RUN"):
        raise ValueError("F60_ORIGINAL_F51_SCIENCE_SCOPE_INVALID")
    c=lambda x:truncated_normal_cdf(x)
    common=c(COMMON_HI)-c(LOW)
    if not math.isclose(common,float(src["common_radio_prior_mass_fraction_now"]),rel_tol=0,abs_tol=2e-12):
        raise ValueError("F60_RADIO_PRIOR_NOT_REPRODUCED")
    prior_low=c(LOW)
    prior_high=1-c(PAIR_HI)
    remaining=prior_low+prior_high
    if not math.isclose(remaining,1-0.903910842245011,rel_tol=0,abs_tol=2e-12):
        raise ValueError("F60_F59_PAIR_TAIL_MASS_MISMATCH")
    if not math.isclose(remaining,float(src["remaining_prior_mass_fraction_uncomputed_for_all_seven"])-(c(PAIR_HI)-c(COMMON_HI)),rel_tol=0,abs_tol=2e-12):
        raise ValueError("F60_F51_F59_NESTED_MASS_MISMATCH")
    surfaces=src["surfaces"]
    if len(surfaces)!=6:
        raise ValueError("F60_SIX_KDE_INPUT_MISSING")
    comparisons=[]
    for k,s in sorted(surfaces.items()):
        old=s["common_24_direct_root_observational_integrals"]
        extended=s["per_EOS_exploratory_actual_direct_C_GR_support_scores_NOT_DIRECTLY_COMPARABLE"]
        for m in ["ENG","MPA1"]:
            if (old[m]["mass_lo_msun"]!=LOW or old[m]["mass_hi_msun"]!=COMMON_HI
                or extended[m]["mass_lo_msun"]!=LOW or extended[m]["mass_hi_msun"]!=PAIR_HI
                or not math.isclose(float(extended[m]["mass_prior_coverage"]),c(PAIR_HI)-c(LOW),abs_tol=2e-12)):
                raise ValueError("F60_PAIR_SUPPORT_NOT_MATCHED")
        ENG=float(extended["ENG"]["likelihood_full_radio_prior_window_contribution"])
        MPA1=float(extended["MPA1"]["likelihood_full_radio_prior_window_contribution"])
        if not all(map(math.isfinite,(ENG,MPA1))) or not (MPA1>ENG>=0):
            raise ValueError("F60_PAIRWISE_ORDER_DRIFT")
        gap=MPA1-ENG
        comparisons.append({
            "kde":k,
            "known_MPA1_minus_ENG_integral_gap":gap,
            "unknown_high_tail_mean_ENG_minus_MPA1_needed_if_low_tail_mean_difference_is_zero":gap/prior_high,
            "necessary_sufficient_condition_for_ENG_to_beat_MPA1":
                "q_low*(T_ENG_low-T_MPA1_low) + q_high*(T_ENG_high-T_MPA1_high) > known_gap",
        })
    targets=[]
    for x in TARGETS:
        span=c(x)-c(LOW)
        targets.append({
            "upper_mass_msun_target_ONLY_IF_PHYSICALLY_STABLE_MODEL_BRANCH_EXISTS":x,
            "mass_prior_coverage_inside_1p89_to_target":span,
            "prior_mass_still_outside_window":1-span,
            "prior_mass_above_target":1-c(x),
        })
    return {
        "schema":"F60_F51_locked_analytic_two_sided_gaussian_tail_v1",
        "status":"PRIOR_TAIL_GEOMETRY_VALIDATED_PHYSICAL_EOS_BRANCH_NOT_RUN",
        "original_F51_SHA256":SOURCE_SHA256,
        "gaussian_radio_mass_prior":{"mu_msun":MU,"sigma_msun":SIGMA,"normalized_within_z":TRUNC_Z},
        "known_pair_interval_msun":[LOW,PAIR_HI],
        "mass_prior_below_1p89":prior_low,
        "mass_prior_above_2p175":prior_high,
        "total_outside_pair_interval":remaining,
        "fraction_of_uncomputed_prior_ABOVE_2p175":prior_high/remaining,
        "conditional_only_comparisons":comparisons,
        "hypothetical_upper_mass_extension_targets":targets,
        "limitations":[
            "Radio mass prior N(2.082,0.0703) truncated +/-5sigma comes from already established F51 lineage; this is analytic partition, not new observation",
            "F42 modified ENG/MPA1 pair only, not original seven nuclear EOS",
            "Mass-prior probability does not prove a physical/stable C/GR solution exists at the target mass",
            "The low-tail likelihood remains unknown, so high-tail-only reversal thresholds require equal low-tail means and are not unconditional guarantees",
            "APR4_EPP and WFF1 have not demonstrated matched 2.175 support: no seven-way extended winner",
            "X-PSI source-native photon likelihood, global stability, original nuclear EOS Bayes and tail bounds NOT_ESTABLISHED",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--f51",default="research/j0740/f51/F51_results.json")
    p.add_argument("--out",default="results/F60/F60_two_sided_prior_tail.json")
    args=p.parse_args()
    res=inspect(Path(args.f51).read_bytes())
    target=Path(args.out);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(res,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("F60 analytic radio mass prior: low {:.9%}, high {:.9%}, q_high/q {:.4%}; no new GR".format(
        res["mass_prior_below_1p89"],res["mass_prior_above_2p175"],res["fraction_of_uncomputed_prior_ABOVE_2p175"]))


if __name__=="__main__":
    main()
