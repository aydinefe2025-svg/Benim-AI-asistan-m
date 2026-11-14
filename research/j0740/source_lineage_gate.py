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
    """Require verified physical source files, not mere copied metadata labels.

    The manifest is from an explicitly matched gamma NxX run. The evidence
    files must exist locally and their current contents must hash to what the
    manifest records. Run-specific inference version must be extracted from an
    original SHA-verified out_ log: the README covers v0.7.10–v1.2.1,
    so hardcoding v1.2.1 would be misleading. Mere ST-U names are insufficient.
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
        "verified_run_identity": "exact_gamma_NxX_lp40k_se001_source_and_prior",
    }
    for k, value in must.items():
        if m.get(k) != value:
            raise RunLineageNotProven(f"Source-run manifest {k} missing/mismatched; refusing proxy inference")
    for key in ("matching_prior", "matching_runner", "matching_sampler_config", "matching_run_log"):
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
    # The Zenodo README explicitly says inference versions vary by RUN and that
    # the original out_ header, not the main.py comment or publication headline,
    # records the version. Require source bytes and a checked log artifact.
    log_entry = m["matching_run_log"]
    log_member = log_entry["original_archive_member"].replace("\\", "/")
    if not (log_member.startswith(PUBLISHED_HEADLINE_OUTPUT_DIR)
            and Path(log_member).name.startswith("out_")):
        raise RunLineageNotProven("Run log must be an original headline ST-U out_ member")
    run_log = Path(log_entry["local_path"]).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?im)\bX[\s-]?PSI\b[^\r\n]{0,90}?\bv?(\d+\.\d+\.\d+)\b", run_log)
    if not match:
        raise RunLineageNotProven("Cannot find X-PSI version in authenticated out_ run log")
    observed = "v" + match.group(1)
    ver = tuple(int(t) for t in match.group(1).split("."))
    if not ((0, 7, 10) <= ver <= (1, 2, 1)):
        raise RunLineageNotProven("X-PSI version outside official Salmi README range")
    if m.get("xpsi_version") != observed:
        raise RunLineageNotProven(
            "Manifest X-PSI version does not match authenticated out_ log: " + observed)
    return {
        "status": "BYTE_IDENTITIES_AND_EXPLICIT_CONFIG_RUN_LABEL_VERIFIED",
        "caution": "Not a native X-PSI photon-likelihood or EOS evidence verification",
        "run": SOURCE_POSTERIOR_RUN,
        "xpsi_version_from_verified_out_log": observed,
        "out_log_sha256": log_entry["sha256"],
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
        "Published Salmi 2024 README confirms gamma NxX outputs map to "
        "STU_NICER_XMM_hr headline run, but original prior/runner byte identity "
        "and run-specific X-PSI version are not yet verified. "
        "Supply a source-byte-verified manifest. "
        "For explicitly labelled archived nonfinal proxy only use historical_proxy_only=True."
    )
