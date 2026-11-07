"""Fail-closed Salmi NICER+XMM source-run provenance gate.

The archived 100k gamma NxX posterior samples MUST NOT be divided by an ST-U
prior copied from another directory unless the source prior, run configuration,
posterior sampling run, and tagged X-PSI engine are explicitly matched.
Checks are about scientific identity, not posterior correctness or likelihood.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SOURCE_POSTERIOR_SHA256 = "4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b"
SOURCE_POSTERIOR_MEMBER = "mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat"
SOURCE_POSTERIOR_RUN = "J0740_gamma_NxX_lp40k_se001"
SOURCE_POSTERIOR_ARCHIVE_MD5 = "ca8e70eeca81feb71321f1a88a24f2f9"
SOURCE_FULL_ARCHIVE_MD5 = "7792c92b9ae1fa404ae5bdd3920ce075"
KNOWN_STU_PRIOR_SHA256 = "5ebcf0a2f11a0f159860ec740e719957066521a501a02c889c5e3da9063207da"
STU_SOURCE_DIRECTORY = "J0740_GAMMA_zenodo/STU/STU_NICER_XMM_hr/STU_modules"


class RunLineageNotProven(ValueError):
    """No verified source-run identity; never report EOS evidence."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_legacy_pair(posterior_metadata: dict, *, prior_source_sha256=KNOWN_STU_PRIOR_SHA256) -> dict:
    """Compare evidence without assuming gamma NxX = archived STU_NICER_XMM_hr."""
    observed = posterior_metadata.get("source_file")
    if observed != Path(SOURCE_POSTERIOR_MEMBER).name:
        raise RunLineageNotProven(f"Unexpected posterior source member: {observed!r}")
    if posterior_metadata.get("source_archive_md5") != SOURCE_POSTERIOR_ARCHIVE_MD5:
        raise RunLineageNotProven("Unexpected original Salmi M-R archive checksum")
    if posterior_metadata.get("settings") != "lp40k_se001":
        raise RunLineageNotProven("Unexpected posterior run sampling settings")
    return {
        "posterior_source_member": SOURCE_POSTERIOR_MEMBER,
        "posterior_run": SOURCE_POSTERIOR_RUN,
        "posterior_subset_sha256": SOURCE_POSTERIOR_SHA256,
        "prior_source_sha256": prior_source_sha256,
        "prior_source_archive_directory": STU_SOURCE_DIRECTORY,
        "posterior_prior_exact_run_link_proven": False,
        "source_run_match_status": "BLOCKED_UNVERIFIED_GAMMA_POSTERIOR_VS_STU_PRIOR_RUN",
        "scientific_use": "Historical sensitivity proxy only; never normalize into EOS posterior or Bayes factors",
        "needed_evidence": [
            "Exact gamma NxX lp40k_se001 sampler configuration from locally verified 12.9GB archive",
            "Exact matching CustomPrior source path and its SHA256 from same run",
            "Exact sampling main source path and its SHA256 from same run",
            "X-PSI engine version and calibration/likelihood input-file paths for this run",
            "Proof the weighted/equal-weight output member belongs to this main and prior",
        ],
    }


def verify_matched_run_manifest(manifest_path: str | Path) -> dict:
    """Require verified physical source files, not mere copied metadata labels.

    The manifest is from an explicitly matched gamma NxX run. The evidence
    files must exist locally and their current contents must hash to what the
    manifest records. Crucially, a legacy STU file name and a gamma label alone
    are not evidence of a shared sampling run.
    """
    path = Path(manifest_path)
    m = json.loads(path.read_text(encoding="utf-8"))
    must = {
        "provenance_schema": "j0740-gamma-nxx-run-match-v1",
        "posterior_subset_sha256": SOURCE_POSTERIOR_SHA256,
        "posterior_source_member": SOURCE_POSTERIOR_MEMBER,
        "posterior_run": SOURCE_POSTERIOR_RUN,
        "full_archive_md5": SOURCE_FULL_ARCHIVE_MD5,
        "source_archive_md5": SOURCE_POSTERIOR_ARCHIVE_MD5,
        "xpsi_version": "v1.2.1",
        "verified_run_identity": "exact_gamma_NxX_lp40k_se001_source_and_prior",
    }
    for k, value in must.items():
        if m.get(k) != value:
            raise RunLineageNotProven(f"Source-run manifest {k} missing/mismatched; refusing proxy inference")
    for key in ("matching_prior", "matching_runner", "matching_sampler_config"):
        ent = m.get(key)
        if not isinstance(ent, dict):
            raise RunLineageNotProven(f"Missing exact source entry {key}")
        source_path = ent.get("local_path")
        h = ent.get("sha256")
        if not source_path or not isinstance(h, str) or len(h) != 64:
            raise RunLineageNotProven(f"Incomplete {key} byte identity")
        p = Path(source_path)
        if not p.is_file() or _sha256(p) != h:
            raise RunLineageNotProven(f"{key} byte hash fails; no verified run linkage")
        if not ent.get("original_archive_member", "").strip():
            raise RunLineageNotProven(f"{key} lacks original tar member provenance")
    # Require an explicit run-to-run binding, not merely shared ST-U model labels.
    if m.get("binding_proof") != "source_sampler_configuration_names_exact_posterior_run":
        raise RunLineageNotProven("No demonstrated gamma posterior-to-prior run binding")
    config = Path(m["matching_sampler_config"]["local_path"]).read_text(encoding="utf-8")
    if SOURCE_POSTERIOR_RUN not in config:
        raise RunLineageNotProven("Sampler configuration does not name the exact posterior run")
    return {
        "status": "BYTE_IDENTITIES_AND_EXPLICIT_CONFIG_RUN_LABEL_VERIFIED",
        "caution": "Not a native X-PSI photon-likelihood or EOS evidence verification",
        "run": SOURCE_POSTERIOR_RUN,
    }


def require_proven_lineage(manifest_path=None, *, historical_proxy_only=False) -> dict:
    if manifest_path:
        return verify_matched_run_manifest(manifest_path)
    if historical_proxy_only:
        return {
            "status": "UNVERIFIED_HISTORICAL_PROXY_ONLY",
            "caution": "No matched 15D X-PSI source prior, not EOS Bayes evidence",
        }
    raise RunLineageNotProven(
        "Source gamma NxX posterior and STU_NICER_XMM_hr prior are not confirmed "
        "as the same sampling run. Supply a verified source-run manifest. "
        "For explicitly labelled archived nonfinal proxy only use historical_proxy_only=True."
    )
