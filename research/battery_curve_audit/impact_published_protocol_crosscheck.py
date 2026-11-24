"""Conservative source-text mathematics for Wei et al. (2025) impact groups.

This is NOT an individual-specimen experiment, calibrated force/charge trace,
causal impact threshold, survival model or physical battery safety certification.

Publisher article: https://doi.org/10.11883/bzycj-2024-0312
Original paper, sections 1.1-1.3, figures 5/10/11.
Published group CSV is existing CANO Library evidence, SHA256 pinned.
"""
from __future__ import annotations

import csv
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import io
import json
from pathlib import Path
import sys

PIN = 'c676a14ec659c1429ff92de1484906e1f67a4693d4bd6d7e543bd28dc41911f3'
DOI = '10.11883/bzycj-2024-0312'
D = Decimal
MASS_KG = D('0.84')
NOMINAL_CAPACITY_MAH = D('850')
FRESH_FAILURE_DISPLACEMENT_MM = D('3.46')
FRESH_FAILURE_DEFORMATION_ENERGY_J = D('21.00')
# Source: figure 5(a), figure 10(b,d), original methodological section 1.2.
# These are PUBLISHED GROUP SUMMARY readings, not per-specimen observations.
EXTERNAL_REPORT = {
    3: {'speed_m_s': D('2.67'), 'loss_mah': D('4.57'),
        'failure_displacement_mm': D('2.86'), 'failure_energy_j': D('12.63')},
    5: {'speed_m_s': D('3.45'), 'loss_mah': D('52.67'),
        'failure_displacement_mm': D('2.76'), 'failure_energy_j': D('11.04')},
    7: {'speed_m_s': D('4.08'), 'loss_mah': D('100.33'),
        'failure_displacement_mm': D('2.32'), 'failure_energy_j': D('6.88')},
}
REQUIRED = ('impact_energy_joule', 'capacity_retained_pct_of_fresh',
            'capacity_loss_pct_vs_fresh', 'internal_resistance_increase_pct_vs_fresh',
            'failure_displacement_decrease_pct_vs_fresh',
            'failure_deformation_energy_decrease_pct_vs_fresh', 'grain', 'source_doi')


def read_publisher_derived_csv(data: bytes) -> list[dict]:
    """Reject any changes to the three previously archived source-summary rows."""
    if not isinstance(data, bytes) or sha256(data).hexdigest() != PIN:
        raise ValueError('SOURCE_REVIEW_REQUIRED: archived summary sha256 mismatch')
    r = csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if tuple(r.fieldnames or ()) != REQUIRED:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source schema mismatch')
    rows = []
    for item in r:
        if None in item or item['source_doi'] != DOI or 'group' not in item['grain']:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source identity/grain conflict')
        e = int(item['impact_energy_joule'])
        if e not in EXTERNAL_REPORT:
            raise ValueError('SOURCE_REVIEW_REQUIRED: unrecognized impact energy')
        v = {k:D(item[k]) for k in REQUIRED[1:6]}
        if not all(x.is_finite() for x in v.values()):
            raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite reported number')
        if v['capacity_retained_pct_of_fresh'] + v['capacity_loss_pct_vs_fresh'] != D('100'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: retained/loss mismatch')
        rows.append((e,v))
    if len(rows) != 3 or {x[0] for x in rows} != set(EXTERNAL_REPORT):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing/duplicate impact group')
    return sorted(rows)


def inferred_reference_interval(loss_mah: Decimal, loss_percent: Decimal) -> tuple[Decimal,Decimal]:
    """Conservative enclosing interval under decimal display rounding only.

    loss mAh to 0.01 mAh; remaining capacity to 0.1 percentage point.
    No asserted equality of fresh-cell baselines between experiments.
    """
    if (not isinstance(loss_mah,Decimal) or not isinstance(loss_percent,Decimal)
            or not loss_mah.is_finite() or not loss_percent.is_finite()
            or loss_mah <= D('.005') or loss_percent <= D('.05')
            or loss_percent >= D('99.95')):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid published capacity/precision')
    lo_q = loss_mah - D('.005')
    hi_q = loss_mah + D('.005')
    lo_pct = loss_percent - D('.05')
    hi_pct = loss_percent + D('.05')
    return (D('100') * lo_q / hi_pct, D('100') * hi_q / lo_pct)


def run(data:bytes) -> dict:
    rows = read_publisher_derived_csv(data)
    groups = []
    interval = []
    for energy, source in rows:
        note = EXTERNAL_REPORT[energy]
        # 0.5*m*v²: checks approximate reported energy labels, not the drop-impact
        # absorbed energy, deformation work, acceleration, impulse or force history.
        calculated_kinetic = MASS_KG * note['speed_m_s']**2 / 2
        if abs(calculated_kinetic - D(energy)) > D('0.02'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: published impact velocity incompatible with stated energy')
        pct = source['capacity_loss_pct_vs_fresh']
        q_lo, q_hi = inferred_reference_interval(note['loss_mah'], pct)
        interval.append((q_lo,q_hi))
        failure_loss_disp = (D('1')-note['failure_displacement_mm']/FRESH_FAILURE_DISPLACEMENT_MM)*100
        failure_loss_energy = (D('1')-note['failure_energy_j']/FRESH_FAILURE_DEFORMATION_ENERGY_J)*100
        if abs(failure_loss_disp-source['failure_displacement_decrease_pct_vs_fresh'])>D('1.5'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: published approximate displacement disagreement')
        if abs(failure_loss_energy-source['failure_deformation_energy_decrease_pct_vs_fresh'])>D('1.5'):
            raise ValueError('SOURCE_REVIEW_REQUIRED: published approximate deformation energy disagreement')
        groups.append({
            'energy_group_J': energy,
            'publisher_impact_speed_m_per_s': str(note['speed_m_s']),
            'kinetic_energy_from_mass_and_speed_J': str(calculated_kinetic.quantize(D('.000001'))),
            'difference_from_nominal_energy_J': str((calculated_kinetic-D(energy)).quantize(D('.000001'))),
            'publisher_capacity_loss_mAh': str(note['loss_mah']),
            'publisher_capacity_retained_percent': str(source['capacity_retained_pct_of_fresh']),
            'publisher_capacity_loss_percent': str(pct),
            'published_nominal_capacity_mAh': str(NOMINAL_CAPACITY_MAH),
            'simple_loss_over_nominal_850mAh_percent':str((note['loss_mah']/NOMINAL_CAPACITY_MAH*100).quantize(D('.000001'))),
            'compatible_reference_capacity_interval_mAh_if_percent_and_mAh_share_same_baseline': [str(q_lo.quantize(D('.00001'))), str(q_hi.quantize(D('.00001')))],
            'publisher_failure_displacement_mm': str(note['failure_displacement_mm']),
            'derived_failure_displacement_loss_percent': str(failure_loss_disp.quantize(D('.00001'))),
            'publisher_failure_deformation_energy_J': str(note['failure_energy_j']),
            'derived_failure_deformation_energy_loss_percent': str(failure_loss_energy.quantize(D('.00001'))),
            'reported_approx_internal_resistance_rise_percent':str(source['internal_resistance_increase_pct_vs_fresh']),
            'substantial_mechanical_loss_even_with_small_electrical_loss_observed':
               energy==3 and pct<=D('1') and failure_loss_energy>=D('30'),
            'independent_specimen_measurement_performed':False,
        })
    common_lo=max(x[0] for x in interval)
    common_hi=min(x[1] for x in interval)
    return {'schema':'cano.battery.wei2025.impact-group-source-numerical-consistency.v1',
        'source_doi':DOI,'source_publisher_article':'https://doi.org/'+DOI,
        'publisher_derived_csv_sha256':PIN,
        'reported_impact_groups':3,'source_grain':'PUBLISHED_GROUP_SUMMARIES_NOT_PER_CELL',
        'nominal_cell_capacity_mAh':'850', 'impact_mass_kg':str(MASS_KG),
        'fresh_failure_displacement_mm':str(FRESH_FAILURE_DISPLACEMENT_MM),
        'fresh_failure_deformation_energy_J':str(FRESH_FAILURE_DEFORMATION_ENERGY_J),
        'kinetic_energy_check_from_paper_setup_only':True,
        'capacity_baseline_math_conditional_on_common_baseline_and_display_rounding':True,
        'common_reference_baseline_math_possible':common_lo<=common_hi,
        'conditional_common_reference_baseline_interval_mAh':
            [str(common_lo.quantize(D('.00001'))),str(common_hi.quantize(D('.00001')))] if common_lo<=common_hi else None,
        'nominal_850mAh_falls_inside_conditional_common_baseline':common_lo<=NOMINAL_CAPACITY_MAH<=common_hi,
        'impact_groups':groups,
        'crucial_3J_observation':'0.6pct capacity loss but approx 40pct secondary compression deformation energy loss',
        'original_individual_cell_rows_retrieved':False,
        'published_group_errorbars_numeric_limits_retrieved':False,
        'exact_mechanical_electrical_sample_identity_verified':False,
        'dated_instrument_calibration_verified':False,
        'same_cell_mechanical_electrical_causality_established':False,
        'bayreuth_aging_cells_paired_with_impact_cells':False,
        'field_FPR_FNR_established':False,
        'production_release_allowed':False,
        'decision':'ORIGINAL_PAPER_SETUP_AND_AGGREGATE_ARITHMETIC_REPRODUCED_RESEARCH_ONLY'}


def main(argv=None):
    a=list(sys.argv[1:] if argv is None else argv)
    if len(a)!=2:print('usage: MODULE PUBLISHER_DERIVED_CSV OUTPUT_JSON',file=sys.stderr);return 2
    source=Path(a[0]);dest=Path(a[1])
    if dest.exists() or not dest.parent.is_dir():print('REVIEW_REQUIRED: output exists/missing dir',file=sys.stderr);return 2
    try:
        out=run(source.read_bytes())
        dest.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf8')
        print('WEI2025_PUBLISHED_IMPACT_GROUP_PROTOCOL',len(out['impact_groups']),
              out['common_reference_baseline_math_possible'],
              out['nominal_850mAh_falls_inside_conditional_common_baseline'])
        return 0
    except (OSError,ValueError,TypeError,UnicodeError,csv.Error) as ex:
        print('SOURCE_REVIEW_REQUIRED:',str(ex)[:200],file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())