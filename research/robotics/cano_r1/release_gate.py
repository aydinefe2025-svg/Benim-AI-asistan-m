"""Fail-closed physical release gate. No hardware can be enabled from this code."""
from dataclasses import dataclass,asdict
from assembly_model import ORIG_START,START,tip_distance_mm

# Only an explicit independent measurement can satisfy each gate. This package
# deliberately contains no actuators, motor drivers, robot IPs or command code.
REQUIRED_EVIDENCE=(
    'measured_motor_torque_speed_curves',
    'measured_motor_and_gearbox_masses_inertias',
    'measured_material_and_print_strength_tests',
    'measured_shaft_bore_fit_and_clearance',
    'tested_gripper_actuator_and_end_effector',
    'measured_payload_and_task_pose_tolerance',
    'validated_fastener_bearing_and_cable_routes',
    'reproduced_full_hardware_mass_dynamics',
    'independent_kinematic_CAD_and_CI_acceptance',
    'independent_bench_safety_test_authorization',
)


def release_status(evidence=None, max_task_shift_mm=5.):
    evidence=evidence or {}
    # Evidence is intentionally immutable/missing in this source-only release.
    missing=[k for k in REQUIRED_EVIDENCE if evidence.get(k) is not True]
    tip_shift=tip_distance_mm(ORIG_START,START)
    task_gate=tip_shift<=max_task_shift_mm
    return {
        'physical_release_allowed':False, # hard lock; no hardware transition in this package
        'stage':'VIRTUAL_CAD_BETA_ONLY',
        'missing_independent_hardware_evidence':missing,
        'assumed_task_tolerance_mm':max_task_shift_mm,
        'start_tip_shift_mm':round(tip_shift,6),
        'task_position_gate_passed':task_gate,
        'reason':'No hardware access; actuator/gripper/material/safety data absent. Never treat a simulation as physical acceptance.'
    }