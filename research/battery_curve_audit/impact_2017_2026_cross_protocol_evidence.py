"""Reproducible cross-study *evidence separation*, not a damage-prediction model.

Study sources are four distinct primary experiments, not 4 independent
replications of the same protocol. Capacity, second-load energy and
one-week survivability are separate endpoints. In particular, high
retained capacity CANNOT certify intact mechanical cell structure.
Original articles:
  Ebert et al. (2017), CoFAT, https://mediatum.ub.tum.de/doc/1378502/534701.pdf
  Stark Goodman et al. (2020), doi:10.1016/j.est.2020.101244
  Wei et al. (2025), doi:10.11883/bzycj-2024-0312
  Sherman & Bombik (2026), doi:10.3390/batteries12060217
No author-request-only raw cell data is manufactured.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


SOURCES = (
  {
    "study_id": "ebert_2017_cofat",
    "source": "https://mediatum.ub.tum.de/doc/1378502/534701.pdf",
    "mechanical_protocol": "vehicle_crash_acceleration_pulse",
    "physical_cell_format": "panasonic_ncr18650pf_cylindrical",
    "capacity_endpoint": "one_off_heavy_ncap_crash_immediate_loss",
    "capacity_loss_percent_interval": [2.0, 3.0],
    "impact_energy_joules": None,
    "one_week_survival": None,
    "cross_specimen_raw_paired_capacity_public": False,
    "notes": "Source conclusion approximate 2-3% NCAP, not joule impact; 100% pre-crash SOC and changing 25C/45C characterization."
  },
  {
    "study_id": "goodman_2020_three_point_bend",
    "source": "https://doi.org/10.1016/j.est.2020.101244",
    "mechanical_protocol": "three_point_bending",
    "physical_cell_format": "lithium_ion_test_cells",
    "capacity_endpoint": "capacity_vs_control_after_up_to_1000_cycles",
    "capacity_loss_percent_interval": None,
    "capacity_vs_control_significant_difference_reported": False,
    "hidden_high_resistance_short_circuits_reported": True,
    "impact_energy_joules": None,
    "one_week_survival": None,
    "cross_specimen_raw_paired_capacity_public": False,
    "notes": "No statistically detectable capacity or impedance difference DOES NOT establish zero difference; mechanically induced hidden internal shorts occurred."
  },
  {
    "study_id": "wei_2025_energy_impact",
    "source": "https://doi.org/10.11883/bzycj-2024-0312",
    "mechanical_protocol": "localized_joule_impact_followed_by_second_load",
    "physical_cell_format": "pouch",
    "capacity_endpoint": "post_impact_fraction_of_new_cell",
    "capacity_retained_pct_by_joule": {"3":99.4,"5":93.6,"7":87.9},
    "secondary_failure_deformation_energy_loss_pct_by_joule": {"3":40.0,"5":47.0,"7":67.0},
    "internal_resistance_increase_pct_by_joule": {"3":4.2,"5":16.2,"7":28.7},
    "one_week_survival": None,
    "cross_specimen_raw_paired_capacity_public": False,
    "notes": "Published aggregate 3/5/7 J outcomes, initially non-failed pouch cells. Sample-resolved before/after raw data not released in examined source."
  },
  {
    "study_id": "sherman_2026_one_week_survival",
    "source": "https://doi.org/10.3390/batteries12060217",
    "mechanical_protocol": "drop_weight_impact_plus_one_week_safety_screen",
    "physical_cell_format": "commercial_pouch",
    "capacity_endpoint": "200_cycle_trajectories_only_for_one_week_survivors",
    "capacity_retained_pct_by_joule": None,
    "one_week_survival": {"3":{"n":15,"survived":15},
                          "5":{"n":15,"survived":9},
                          "7":{"n":15,"survived":0}},
    "cross_specimen_raw_paired_capacity_public": False,
    "notes": "45 separate impacted cells; 7J zero one-week survivors, hence no 7J post-screen capacity trajectory. Raw capacity and HPPC data are on-author-request."
  }
)


def audit() -> dict:
    assert len(SOURCES) == 4 and len({s["study_id"] for s in SOURCES}) == 4
    assert all(s["source"].startswith("https://") for s in SOURCES)
    s17,s20,s25,s26=SOURCES
    assert s17["mechanical_protocol"] != s25["mechanical_protocol"]
    assert s20["mechanical_protocol"] != s25["mechanical_protocol"]
    assert s26["mechanical_protocol"] != s25["mechanical_protocol"]
    assert s25["physical_cell_format"] == "pouch" and s26["physical_cell_format"] == "commercial_pouch"
    assert s25["mechanical_protocol"] != s26["mechanical_protocol"]
    assert s17["impact_energy_joules"] is None
    assert s17["capacity_loss_percent_interval"] == [2.0,3.0]
    assert s20["capacity_vs_control_significant_difference_reported"] is False
    assert s20["hidden_high_resistance_short_circuits_reported"] is True
    for e in ("3","5","7"):
        assert 0 < s25["capacity_retained_pct_by_joule"][e] <= 100
        assert s25["secondary_failure_deformation_energy_loss_pct_by_joule"][e] > 0
    retained_3=s25["capacity_retained_pct_by_joule"]["3"]
    weaker_3=s25["secondary_failure_deformation_energy_loss_pct_by_joule"]["3"]
    assert retained_3 > 99 and weaker_3 >= 40
    assert s26["one_week_survival"]["7"]=={"n":15,"survived":0}
    assert all(not s["cross_specimen_raw_paired_capacity_public"] for s in SOURCES)
    return {
      "evidence_kind":"published_primary_study_aggregate_and_narrative_not_recovered_raw_cell_measurements",
      "source_count":len(SOURCES),
      "study_independent_records":list(SOURCES),
      "observed_counterexample":{
        "study":"wei_2025_energy_impact","impact_j":3,
        "capacity_retained_pct":retained_3,
        "deformation_energy_to_failure_reduction_pct":weaker_3,
        "meaning":"high_capacity_retention_does_not_certify_original_mechanical_integrity",
        "is_direct_paired_individual_cell_data":False
      },
      "independent_hidden_fault_corroboration":{
        "study":"goodman_2020_three_point_bend",
        "capacity_difference_statistically_detected":False,
        "post_abuse_hidden_resistive_short_observed":True,
        "meaning":"failure_to_reject_capacity_difference_is_not_evidence_of_cell_safety"
      },
      "cross_protocol_pooling_allowed":False,
      "nominally_same_7j_does_not_make_experiments_exchangeable":True,
      "cannot_convert_2017_crash_acceleration_pulse_to_joules_from_paper":True,
      "individual_cell_damage_capacity_function_identifiable":False,
      "no_safety_clearance_from_capacity_alone":True,
      "no_raw_or_sensor_recalibration_claim":True,
      "no_2017_or_2020_p_value_fabricated":True
    }


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=audit()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print("FOUR_STUDY_CROSS_PROTOCOL_FALSIFICATION_PASS",a.output)
