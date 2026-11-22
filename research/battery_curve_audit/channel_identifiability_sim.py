"""Source-grounded, non-calibrated battery channel identifiability simulation.

Separate evidence: original Figshare 27 source-derived capacity deltas are *observations*;
a two-channel bounded-additive-discrepancy model is an entirely *hypothetical*
simulation. This simulation cannot attribute anomalies to temperature, protocol,
physical capacity recovery, or instrument error.

Model for each source cell and temperature, in percentage-point delta units:
    observed charge delta = latent change + hypothetical charge offset
    observed discharge delta = latent change + hypothetical discharge offset
    |each offset| <= assumed B percentage points, latent change < 0.
No assertion that these two physical observables share an identical latent variable.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SCHEMA = "cano.battery.figshare25975315.k01-k04-k05-nine-distinct-publisher-source-records-channel-sign.v1"
SOURCE_DOI = "10.6084/m9.figshare.25975315"
COHORTS = ("TP_k01", "TP_k04", "TP_k05")
TEMPS = (10,23,45)
DEFAULT_BOUNDS = ("0.10", "0.25", "0.50", "0.75", "1.00")


def fixed_decimal(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError(f"INVALID_SOURCE_NUMERIC {label}")
    try: x = Decimal(str(value))
    except (InvalidOperation, ValueError): raise ValueError(f"INVALID_SOURCE_NUMERIC {label}") from None
    if not x.is_finite() or abs(x) > 100: raise ValueError(f"INVALID_SOURCE_NUMERIC {label}")
    return x


def _round(x: Decimal, places="0.0001"):
    return float(x.quantize(Decimal(places)))


def load_observations(path: Path):
    raw=path.read_bytes()
    d=json.loads(raw)
    if not isinstance(d,dict) or d.get("schema")!=EXPECTED_SCHEMA or d.get("source_doi")!=SOURCE_DOI:
        raise ValueError("INVALID_ORIGINAL_RECEIPT provenance")
    if (d.get("source_file_records"),d.get("source_temperature_pairs"),
        d.get("original_csv_files_processed"),d.get("original_measurement_rows_examined"))!=(9,27,54,17280862):
        raise ValueError("INVALID_ORIGINAL_RECEIPT counts")
    if set(d.get("cohorts",[]))!=set(COHORTS) or len(d.get("cohorts",[]))!=3:
        raise ValueError("INVALID_ORIGINAL_RECEIPT cohorts")
    if d.get("publisher_lab_serial_unique_across_all_nine") is not True:
        raise ValueError("INVALID_ORIGINAL_RECEIPT original identities")
    for flag in ("physical_custody_authenticated","instrument_calibration_validated", "field_FPR_FNR_established",
                 "temperature_causality_established","storage_only_causal_degradation_established","production_release_allowed"):
        if d.get(flag) is not False: raise ValueError("UNSUPPORTED_PHYSICAL_EVIDENCE_CLAIM "+flag)
    rows=d.get("source_results")
    if not isinstance(rows,list) or len(rows)!=27:raise ValueError("INVALID_ORIGINAL_RECEIPT pair_count")
    seen=set();by_cohort=Counter();out=[]
    for v in rows:
        if not isinstance(v,dict) or v.get("cohort") not in COHORTS or type(v.get("temperature_C")) is not int or v["temperature_C"] not in TEMPS:
            raise ValueError("INVALID_ORIGINAL_RECEIPT pair")
        fid=v.get("source_file_id")
        if type(fid) is not int or fid<1:raise ValueError("INVALID_ORIGINAL_RECEIPT file_id")
        pair=(v["cohort"],fid,v["temperature_C"])
        if pair in seen:raise ValueError("INVALID_ORIGINAL_RECEIPT repeated source/temp")
        seen.add(pair)
        c=fixed_decimal(v.get("charge_change_percent"),"charge")
        dd=fixed_decimal(v.get("discharge_change_percent"),"discharge")
        m=fixed_decimal(v.get("mean_change_percent"),"mean")
        if not (-15<c<5 and -15<dd<5 and -15<m<5):raise ValueError("INVALID_ORIGINAL_RECEIPT capacity range")
        both=c<0 and dd<0
        mixed=not both
        if both is not v.get("both_channels_decline") or mixed is not v.get("mixed_or_zero_channel_sign"):
            raise ValueError("INVALID_ORIGINAL_RECEIPT source classification")
        if m>=0:raise ValueError("INVALID_ORIGINAL_RECEIPT mean should decline")
        out.append({"cohort":v["cohort"],"source_file_id":fid,"temperature_C":v["temperature_C"],
                    "charge_change_percent":c,"discharge_change_percent":dd,"mean_change_percent":m,
                    "mixed_channel_sign_observed":mixed})
        by_cohort[v["cohort"]]+=1
    if any(by_cohort[x]!=9 for x in COHORTS) or len({(x["cohort"],x["source_file_id"]) for x in out})!=9:
        raise ValueError("INVALID_ORIGINAL_RECEIPT cohort grain")
    if any({x["temperature_C"] for x in out if (x["cohort"],x["source_file_id"])==s}!=set(TEMPS)
           for s in {(x["cohort"],x["source_file_id"]) for x in out}):
        raise ValueError("INVALID_ORIGINAL_RECEIPT missing temperature")
    if sum(x["mixed_channel_sign_observed"] for x in out)!=4:
        raise ValueError("INVALID_ORIGINAL_RECEIPT sign count")
    out.sort(key=lambda x:(x["cohort"],x["source_file_id"],x["temperature_C"]))
    return raw,out


def feasible_under_bound(charge_delta,discharge_delta,bound):
    """Existence of hypothetical latent loss <0 with two additive offsets in [-B,B]."""
    c, d, b=map(Decimal,(str(charge_delta),str(discharge_delta),str(bound)))
    if b<0 or b>100: raise ValueError("INVALID_SIMULATION_BOUND")
    lower=max(c-b,d-b)
    upper=min(c+b,d+b)
    return lower<=upper and lower<0 and (upper<0 or lower<0)


def simulate(source:Path, bounds=DEFAULT_BOUNDS):
    source_bytes,obs=load_observations(source)
    bvalues=[fixed_decimal(v,"hypothetical_bound_pp") for v in bounds]
    if any(v<0 or v>5 for v in bvalues) or len(set(bvalues))!=len(bvalues) or bvalues!=sorted(bvalues):
        raise ValueError("INVALID_SIMULATION_BOUNDS")
    details=[]
    for v in obs:
        c,d=v["charge_change_percent"],v["discharge_change_percent"]
        midpoint=(c+d)/2
        # Exact minimal half-gap B for common negative latent model on these data
        if midpoint>=0: raise ValueError("LATENT_NEGATIVE_MODEL_INCOMPATIBLE_WITH_SOURCE_MIDPOINT")
        bmin=abs(c-d)/2
        details.append({"cohort":v["cohort"],"source_file_id":v["source_file_id"],"temperature_C":v["temperature_C"],
                        "observed_charge_change_percent":_round(c),"observed_discharge_change_percent":_round(d),
                        "observed_mean_change_percent":_round(v["mean_change_percent"]),
                        "observed_mixed_channel_sign":v["mixed_channel_sign_observed"],
                        "hypothetical_equal_channel_latent_percent":_round(midpoint),
                        "minimum_symmetric_offset_bound_pp":_round(bmin),
                        "signed_offsets_at_minimum_pp":{"charge":_round(c-midpoint),"discharge":_round(d-midpoint)},
                        "observed_channel_gap_pp":_round(abs(c-d))})
    scenarios=[]
    for b in bvalues:
        per_temp={str(t):sum(feasible_under_bound(v["charge_change_percent"],v["discharge_change_percent"],b)
                             for v in obs if v["temperature_C"]==t) for t in TEMPS}
        scenarios.append({"hypothetical_channel_offset_cap_pp":str(b),
                          "source_conditions_feasible_under_ASSUMED_model":sum(per_temp.values()),
                          "source_conditions_total":27,"by_temperature_feasible_of_9":per_temp,
                          "measured_instrument_bound":False,"field_test":False})
    thresholds={str(t):_round(max(Decimal(str(d["minimum_symmetric_offset_bound_pp"])) for d in details if d["temperature_C"]==t)) for t in TEMPS}
    return {"schema":"cano.simulation.battery-nine-source-two-channel-identifiability.v1",
      "goal_key":"battery-nine-source-channel-observability-hypothetical-bounds-20261122",
      "evidence_partition":{"input_kind":"PUBLISHER_ORIGINAL_MEASUREMENTS_DERIVED_PREVIOUSLY",
         "simulation_kind":"MATHEMATICAL_COUNTERFACTUAL_UNCALIBRATED",
         "original_source_record_sha256":hashlib.sha256(source_bytes).hexdigest(),
         "original_source_doi":SOURCE_DOI,"original_csv_files_according_to_prior_receipt":54,
         "original_rows_according_to_prior_receipt":17280862,
         "real_waveforms_reintegrated_this_run":False,"independent_physical_test_performed":False},
      "model":{"name":"latent_common_percent_change_plus_independent_bounded_channel_offsets",
          "units":"percentage points of channel ET-to-AT relative change",
          "channel_observations_share_latent_percent_change":"HYPOTHESIS_ONLY",
          "positive_bound_is_user_defined_not_instrument_calibration":True,
          "no_temperature_physics_specified":True,"deterministic_exact_decimal_algebra":True},
      "source_labeled_physical_cell_records":9,"source_temperature_observations":27,
      "observed_opposite_or_zero_direction_pairs":sum(x["mixed_channel_sign_observed"] for x in obs),
      "minimum_bound_pp_required_to_fit_all_27_under_model":_round(max(Decimal(str(x["minimum_symmetric_offset_bound_pp"])) for x in details)),
      "minimum_bound_pp_required_by_temperature":thresholds,
      "hypothetical_scenarios":scenarios,"source_observations_and_simulated_offsets":details,
      "physical_aging_causality_established":False,"temperature_causality_established":False,
      "instrument_uncertainty_measured":False,"field_FPR_FNR_established":False,"production_release_allowed":False,
      "interpretation":"A fitting scenario demonstrates non-identifiability under chosen artificial bounds, NOT that measurement error caused discordance."}


def main():
    a=argparse.ArgumentParser()
    a.add_argument("--source",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    args=a.parse_args()
    if args.out.exists():raise SystemExit("OUTPUT_EXISTS_NO_OVERWRITE")
    d=simulate(args.source)
    args.out.write_text(json.dumps(d,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf8")
    print("SIMULATION_ONLY_NO_CAUSAL_CLAIM",d["minimum_bound_pp_required_to_fit_all_27_under_model"],
          [(v["hypothetical_channel_offset_cap_pp"],v["by_temperature_feasible_of_9"]) for v in d["hypothetical_scenarios"]])


if __name__=="__main__":main()
