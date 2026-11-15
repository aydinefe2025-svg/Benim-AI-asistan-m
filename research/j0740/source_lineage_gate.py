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
import re

SOURCE_POSTERIOR_SHA256 = "4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b"
SOURCE_POSTERIOR_MEMBER = "mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat"
SOURCE_POSTERIOR_RUN = "J0740_gamma_NxX_lp40k_se001"
SOURCE_POSTERIOR_ARCHIVE_MD5 = "ca8e70eeca81feb71321f1a88a24f2f9"
SOURCE_FULL_ARCHIVE_MD5 = "7792c92b9ae1fa404ae5bdd3920ce075"
KNOWN_STU_PRIOR_SHA256 = "5ebcf0a2f11a0f159860ec740e719957066521a501a02c889c5e3da9063207da"
STU_SOURCE_DIRECTORY = "J0740_GAMMA_zenodo/STU/STU_NICER_XMM_hr/STU_modules"



PUBLISHED_HEADLINE_RUNNER = "STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py"
PUBLISHED_HEADLINE_PRIOR = "STU/STU_NICER_XMM_hr/STU_modules/CustomPrior_GLS_compressed_scaling_Dfix.py"
PUBLISHED_HEADLINE_OUTPUT_DIR = "STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/"
PUBLISHED_README = "https://zenodo.org/records/10519473/files/README.md?download=1"
PUBLISHED_README_MD5 = "ed363c6d252a0a6ef177f8d45757e50e"


def documented_headline_mapping() -> dict:
    """Original Zenodo 10519473 README, 'Analysis scripts' + 'Posterior samples'.

    'gamma_NxX' is the GAMMA/NICER dataset label; the original Salmi 2024
    headline source code is the ST-U geometry run in STU_NICER_XMM_hr.
    Documentary run identity does not by itself check original file bytes.
    """
    return {
        "source": PUBLISHED_README,
        "readme_md5": PUBLISHED_README_MD5,
        "posterior_source": SOURCE_POSTERIOR_MEMBER,
        "runner_member": PUBLISHED_HEADLINE_RUNNER,
        "prior_member": PUBLISHED_HEADLINE_PRIOR,
        "output_directory": PUBLISHED_HEADLINE_OUTPUT_DIR,
        "emission_geometry": "ST-U two circular uniform-temperature hot regions",
        "run_mapping": "PUBLISHED_README_HEADLINE_RUN_DIRECTORY_CONFIRMED",
        "exact_original_prior_bytes_verified": False,
        "run_specific_xpsi_version_verified": False,
        "native_likelihood_verified": False,
    }


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
        "posterior_prior_same_run_directory_documented": True,
        "posterior_prior_exact_original_file_bytes_verified": False,
        "posterior_prior_exact_run_link_proven": False,
        "source_run_match_status": "PUBLISHED_README_CONFIRMS_GAMMA_NXX_IS_STU_HEADLINE_RUN_FILE_BYTES_PENDING",
        "published_mapping": documented_headline_mapping(),
        "scientific_use": "Historical sensitivity proxy only; never normalize into EOS posterior or Bayes factors",
        "needed_evidence": [
            "SHA256-verify original published STU headline runner and CustomPrior bytes from already-owned 12.9GB tar",
            "Check original out_ run header for the actual inference X-PSI version (README lists versions v0.7.10–v1.2.1)",
            "Check effective prior nuisance calibration/likelihood input files in that run before using any Bayes evidence",
        ],
    }


def verify_matched_run_manifest(manifest_path: str | Path) -> dict:
    """Require publisher README mapping plus the five byte-pinned source files.

    The published gamma_NxX posterior prefix is not a literal ST-U sampler
    config token. The old literal-name test yielded a false negative.
    The new v2 manifest checks the genuine runner/prior/config/out_/stats
    archive-member paths and their fixed source SHA-256 hashes instead.
    Historical 12.9GB checksum metadata does not imply a new read today.
    """
    from published_source_lineage import verify_published_headline_manifest
    try:
        return verify_published_headline_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        raise RunLineageNotProven(str(exc)) from exc


def require_proven_lineage(manifest_path=None, *, historical_proxy_only=False) -> dict:
    if manifest_path:
        return verify_matched_run_manifest(manifest_path)
    if historical_proxy_only:
        return {
            "status": "UNVERIFIED_HISTORICAL_PROXY_ONLY",
            "caution": "No matched 15D X-PSI source prior, not EOS Bayes evidence",
        }
    raise RunLineageNotProven(
        "Published Salmi 2024 README confirms gamma NxX outputs map to "
        "STU_NICER_XMM_hr headline run, but original prior/runner byte identity "
        "and run-specific X-PSI version are not yet verified. "
        "Supply a source-byte-verified manifest. "
        "For explicitly labelled archived nonfinal proxy only use historical_proxy_only=True."
    )
