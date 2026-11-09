"""Portable, blind-safe progress backups for human benchmark labels."""
from __future__ import annotations

import json

FORMAT = "cano-human-label-progress"
VERSION = 1
MAX_BACKUP_BYTES = 64_000
VALID_LABELS = frozenset({"supported", "contradicted", "insufficient"})


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate backup field")
        result[key] = value
    return result


def _validated_cohorts(cohorts, allowed_case_ids):
    if not isinstance(cohorts, dict) or not isinstance(allowed_case_ids, dict):
        raise ValueError("Invalid cohort mapping")
    if set(cohorts) - set(allowed_case_ids):
        raise ValueError("Unknown cohort")
    clean = {}
    for cohort, labels in cohorts.items():
        if not isinstance(cohort, str) or not isinstance(labels, dict):
            raise ValueError("Invalid cohort labels")
        allowed = allowed_case_ids[cohort]
        if set(labels) - set(allowed):
            raise ValueError("Unknown case identifier")
        kept = {}
        for case_id, label in labels.items():
            if not isinstance(case_id, str) or not isinstance(label, str) or label not in VALID_LABELS:
                raise ValueError("Invalid human label")
            kept[case_id] = label
        if kept:
            clean[cohort] = kept
    return clean


def encode_human_label_progress(cohorts, allowed_case_ids):
    """Serialize only user labels; never include gold keys or model predictions."""
    clean = _validated_cohorts(cohorts, allowed_case_ids)
    payload = json.dumps(
        {"format": FORMAT, "version": VERSION, "cohorts": clean},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    if len(payload.encode("utf-8")) > MAX_BACKUP_BYTES:
        raise ValueError("Human label backup exceeds size limit")
    return payload


def decode_human_label_progress(payload, allowed_case_ids):
    """Validate imported labels against current cohorts before returning any data."""
    if isinstance(payload, bytes):
        if len(payload) > MAX_BACKUP_BYTES:
            raise ValueError("Human label backup exceeds size limit")
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid backup encoding") from exc
    if (not isinstance(payload, str) or not payload
            or len(payload.encode("utf-8")) > MAX_BACKUP_BYTES):
        raise ValueError("Invalid human label backup")
    try:
        data = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Invalid human label backup JSON") from exc
    if (not isinstance(data, dict)
            or set(data) != {"format", "version", "cohorts"}
            or data.get("format") != FORMAT
            or data.get("version") != VERSION):
        raise ValueError("Unsupported human label backup format")
    return _validated_cohorts(data["cohorts"], allowed_case_ids)
