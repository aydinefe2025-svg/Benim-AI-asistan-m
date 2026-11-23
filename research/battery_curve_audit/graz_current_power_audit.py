"""Original Graz five-cell numerical V/I/P consistency audit (not unit certification).

Publisher ZIP is authenticated before any row decoding. A numerical relation between
three *unlabelled* columns does not establish SI units, phase, capacity or safety.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import random
import re
import statistics
import zipfile
from collections import Counter
from pathlib import Path

from research.battery_curve_audit import graz_source_preflight as source

EXPECTED_SHA256 = '5627a1606b8e378de0e4e4ced99222509bcbbcb725d26da6e7a5fad34aa42fc7'
EXPECTED_ROWS = 1_091_337
CELLS = ('01', '02', '03', '04', '05')
EXPECTED_COLS = ('Time', 'Device', 'Voltage', 'Current', 'Power')
TIME_RE = re.compile(r'^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d-\d{1,6}$')
MAX_PER_CELL_SAMPLES = 3000


def finite(token: str) -> float:
    value = float(token.strip())
    if not math.isfinite(value):
        raise ValueError('nonfinite physical source numeric column')
    return value


def numeric_scale_audit(vi_and_p: list[tuple[float, float, float]]) -> dict:
    """Compare numeric P/(V*I) to 1, .001 and 1000 without declaring units."""
    ratios = []
    for v, i, p in vi_and_p:
        if not all(math.isfinite(x) for x in (v, i, p)):
            raise ValueError('nonfinite source numeric measurement')
        x = v * i
        if abs(x) >= .01:  # avoid artificial large ratios when current ~= 0
            ratios.append(p / x)
    if not ratios:
        return {'eligible_records': 0, 'median_numeric_power_to_voltage_current_ratio': None,
                'numeric_ratio_median_abs_deviation': None,
                'fraction_numerically_near_ratio_1_within_5pct': None,
                'candidate_numeric_ratio_reference': None, 'independent_units_calibrated': False}
    median = statistics.median(ratios)
    mad = statistics.median(abs(x - median) for x in ratios)
    candidates = {'numeric_P_over_VI_0.001': .001, 'numeric_P_over_VI_1': 1.0,
                  'numeric_P_over_VI_1000': 1000.0, 'numeric_P_over_VI_minus_1': -1.0}
    # This is purely a numerical pattern; not a unit declaration.
    near = {key: sum(abs(x - value) <= .05 * abs(value) for x in ratios) / len(ratios)
            for key, value in candidates.items()}
    best_key = max(near, key=near.get)
    return {
        'eligible_records': len(ratios),
        'median_numeric_power_to_voltage_current_ratio': round(median, 9),
        'numeric_ratio_median_abs_deviation': round(mad, 9),
        'fraction_numerically_near_ratio_1_within_5pct': round(near['numeric_P_over_VI_1'], 6),
        'candidate_numeric_ratio_reference': best_key if near[best_key] >= .80 else None,
        'fraction_near_reference_scales': {k: round(v, 6) for k, v in near.items()},
        'independent_units_calibrated': False,
    }


def audit_electrical_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, *, cell: str) -> dict:
    """Single pass over all original rows; deterministic, size-bounded reservoir."""
    rng = random.Random(20261123 + int(cell))
    sample: list[tuple[float, float, float]] = []
    devices = Counter()
    total = 0
    nonzero_numeric_pairs = 0
    zero_current_nonzero_power = 0
    negatives = Counter()
    first_token = last_token = None
    with archive.open(member) as raw:
        header = raw.readline().decode('utf-8-sig', errors='strict').strip()
        if tuple(x.strip() for x in header.split(',')) != EXPECTED_COLS:
            raise ValueError('unlabelled or changed original Time/Device/Voltage/Current/Power header')
        for line_num, raw_line in enumerate(raw, start=2):
            line = raw_line.decode('utf-8-sig', errors='strict').strip()
            if not line:
                continue
            cols = [x.strip() for x in line.split(',')]
            if len(cols) != 5 or not TIME_RE.fullmatch(cols[0]):
                raise ValueError(f'original source electrical row shape/time invalid at {line_num}')
            if not re.fullmatch(r'COM\d+', cols[1]):
                raise ValueError('unknown original device identifier')
            v, i, p = (finite(x) for x in cols[2:])
            if not (0 < v < 10 and abs(i) <= 200 and abs(p) <= 2000):
                raise ValueError('original measurement exceeds constrained numeric range')
            total += 1
            devices[cols[1]] += 1
            first_token = cols[0] if first_token is None else first_token
            last_token = cols[0]
            if i < 0: negatives['negative_current'] += 1
            if p < 0: negatives['negative_power'] += 1
            if abs(i) < 1e-9 and abs(p) > 1e-3: zero_current_nonzero_power += 1
            if abs(v*i) >= .01: nonzero_numeric_pairs += 1
            if len(sample) < MAX_PER_CELL_SAMPLES:
                sample.append((v, i, p))
            else:
                j = rng.randrange(total)
                if j < MAX_PER_CELL_SAMPLES:
                    sample[j] = (v, i, p)
            if total > 800_000:
                raise ValueError('original electrical log exceeded safe row budget')
    if total < 100:
        raise ValueError('original source electrical log too short')
    result = numeric_scale_audit(sample)
    return {
        'physical_cell': cell,
        'publisher_nominal_static_preload_kN': source.CELL_PRELOAD_KN[cell],
        'genuine_original_row_count': total,
        'source_device_labels': dict(sorted(devices.items())),
        'first_timestamp_token': first_token,
        'last_timestamp_token': last_token,
        'nonzero_numeric_vi_rows_total': nonzero_numeric_pairs,
        'rows_with_near_zero_current_and_nonzero_power': zero_current_nonzero_power,
        'negative_current_rows': negatives['negative_current'],
        'negative_power_rows': negatives['negative_power'],
        'bounded_deterministic_reservoir_size': len(sample),
        'numeric_consistency_sample_only': result,
        'calibrated_current_unit_A': False,
        'calibrated_power_unit_W': False,
        'independently_verified_charge_discharge_steps': False,
    }


def inspect_original(blob: bytes, size: int) -> dict:
    certificate = source.inspect_archive(blob, size)
    if certificate['original_zip_sha256'] != EXPECTED_SHA256:
        raise ValueError('different publisher archive even if MD5-checksum is trusted')
    results = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        members = archive.infolist()
        for cell in CELLS:
            owned = [m for m in members if not m.is_dir()
                     and source.explicit_cell_in_path(m.filename) == cell
                     and source.role_for_member(m.filename) == 'charge_discharge_log_candidate']
            if len(owned) != 1:
                raise ValueError(f'expected exactly one original electrical log in cell {cell}')
            results[cell] = audit_electrical_member(archive, owned[0], cell=cell)
    count = sum(item['genuine_original_row_count'] for item in results.values())
    if count != EXPECTED_ROWS:
        raise ValueError(f'original five-cell row count conflict {count}')
    return {
        'goal_key': 'graz-20261123-real-five-cell-power-current-numerical-consistency-v1',
        'source_doi': source.DOI,
        'original_zip_sha256': EXPECTED_SHA256,
        'official_publisher_md5_verified': certificate['publisher_zip_md5_verified'],
        'original_archive_crc_verified': certificate['zip_crc_verified'],
        'real_physical_cells': list(CELLS),
        'real_electrical_rows': count,
        'cells': results,
        'this_is_a_purely_numeric_same_row_relation': True,
        'power_and_current_units_independently_certified': False,
        'controller_program_phase_certified': False,
        'real_clock_alignment_certified': False,
        'real_capacity_Ah_reconstructed': False,
        'real_load_causality_established': False,
        'dynamic_impact_trial': False,
        'physical_production_release_allowed': False,
        'not_a_measured_field_error_rate': True,
        'new_real_physical_experiment_performed': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    original, declared_size = source.get_original()
    result = inspect_original(original, declared_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                      sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
    for cell, item in result['cells'].items():
        c = item['numeric_consistency_sample_only']
        print('ORIGINAL_CELL_POWER_NUMERIC_CONSISTENCY', cell, item['genuine_original_row_count'],
              c['eligible_records'], c['median_numeric_power_to_voltage_current_ratio'],
              c['candidate_numeric_ratio_reference'])
    print('UNIT_AND_CALIBRATION_NOT_AUTHENTICATED_NO_CAPACITY_RELEASE')


if __name__ == '__main__':
    main()