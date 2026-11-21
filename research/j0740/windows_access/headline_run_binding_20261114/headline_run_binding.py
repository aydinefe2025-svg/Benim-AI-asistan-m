"""Conservative cross-name publication/run identity audit for Salmi 2024.

Do not equate the publication's `gamma_NxX` sample prefix with a sampler
configuration filename. The Zenodo README explicitly maps the headline samples
into STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix.

This verifies exact source-file bytes *when local paths are supplied*; it does
not certify complete X-PSI photon likelihoods, rotating-star physics, or EOS Bayes.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Mapping

PINS = {
    "runner": "440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af",
    "prior": "ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93",
    "config": "02592091e8c10d126b10070e0e33515a292d57d750c2a45d624065d056752ede",
    "out_log": "f20ae7db9550a9fd608542c1b43fc9534a3e396df7ef5c2dad66493793caa2de",
    "stats": "779167d6d11e40d21eb733523e4759773ef1e1f9eb913227e8550d7dd30f5b14",
}
PUBLISHED_OUTPUT_DIR = "STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/"
README_MD5 = "ed363c6d252a0a6ef177f8d45757e50e"
POSTERIOR_ARCHIVE_MD5 = "ca8e70eeca81feb71321f1a88a24f2f9"
FULL_ARCHIVE_MD5 = "7792c92b9ae1fa404ae5bdd3920ce075"
KNOWN_STATS_LOGZ = -21889.986812013929
KNOWN_STATS_ERROR = 0.0244091345940078905
EXPECTED_SOURCE_MEMBERS = {
    "runner": "STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py",
    "prior": "STU/STU_NICER_XMM_hr/STU_modules/CustomPrior_GLS_compressed_scaling_Dfix.py",
    "config": "STU/STU_NICER_XMM_hr/STU_modules/config.ini",
    "out_log": PUBLISHED_OUTPUT_DIR + "out_",
    "stats": PUBLISHED_OUTPUT_DIR + "stu_nlive40000_eff0.01_noCONST_noMM_noIS_tol-1stats.dat",
}

class SourceMismatch(ValueError):
    """The purported headline archive binding cannot be accepted."""


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_published_binding(
    artifact_paths: Mapping[str, str | Path],
    archive_members: Mapping[str, str],
    *,
    readme_md5: str,
    source_posterior_archive_path: str | Path,
    stats_logz: float,
    stats_error: float,
    out_logz: float,
    out_error: float,
    full_archive_path: str | Path | None = None,
    readme_local_path: str | Path | None = None,
    expected_file_hashes: Mapping[str, str] = PINS,
) -> dict:
    """Verify a publication-documented, cross-prefix run link from real bytes.

    The optional expected_file_hashes override is for synthetic unit fixtures;
    nondefault pins never yield a publishable provenance outcome.
    """
    if readme_md5.lower() != README_MD5:
        raise SourceMismatch("official Zenodo README identity mismatch")
    readme_checked = readme_local_path is not None
    if readme_checked and digest(Path(readme_local_path), "md5") != README_MD5:
        raise SourceMismatch("published README file bytes MD5 mismatch")
    if digest(Path(source_posterior_archive_path), "md5") != POSTERIOR_ARCHIVE_MD5:
        raise SourceMismatch("published posterior archive MD5 mismatch")
    complete_full_archive = full_archive_path is not None
    if complete_full_archive and digest(Path(full_archive_path), "md5") != FULL_ARCHIVE_MD5:
        raise SourceMismatch("full 12.9 GB publisher archive MD5 mismatch")
    if set(artifact_paths) != set(PINS) or set(archive_members) != set(PINS):
        raise SourceMismatch("missing or unexpected source artifact")
    if set(expected_file_hashes) != set(PINS):
        raise SourceMismatch("invalid expected source hash schema")
    for k, value in EXPECTED_SOURCE_MEMBERS.items():
        if archive_members[k].replace("\\", "/") != value:
            raise SourceMismatch("unexpected publisher archive member: " + k)
        actual = digest(Path(artifact_paths[k]))
        if actual.lower() != expected_file_hashes[k].lower():
            raise SourceMismatch("source byte hash mismatch: " + k)
    version_log = Path(artifact_paths["out_log"]).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"(?im)\bX[\s-]?PSI\b[^\r\n]{0,90}?\bv?(\d+\.\d+\.\d+)\b", version_log)
    if not match:
        raise SourceMismatch("source out_ log lacks X-PSI version")
    version = tuple(map(int, match.group(1).split(".")))
    if not ((0, 7, 10) <= version <= (1, 2, 1)):
        raise SourceMismatch("source X-PSI version outside publisher's range")
    if not (abs(stats_logz - out_logz) <= 1e-8 and abs(stats_error - out_error) <= 1e-10):
        raise SourceMismatch("archived stats/out_ evidence numbers disagree")
    if stats_error < 0 or out_error < 0:
        raise SourceMismatch("invalid evidence uncertainty")
    if abs(stats_logz - KNOWN_STATS_LOGZ) > 1e-8 or abs(stats_error - KNOWN_STATS_ERROR) > 1e-10:
        raise SourceMismatch("evidence values are not the known original logZ and uncertainty")
    test_override = dict(expected_file_hashes) != PINS
    return {
        "status": "PUBLISHER_DIRECTORY_AND_SOURCE_FILE_BYTES_VERIFIED" if not test_override else "SYNTHETIC_TEST_FIXTURE_ONLY",
        "run_link": "PUBLISHER_README_MAPS_GAMMA_NXX_MR_TO_STU_HEADLINE_DIR",
        "source_version_from_out_log": "v" + match.group(1),
        "reported_evidence_values_match": True,
        "full_archive_md5_checked_this_run": complete_full_archive,
        "official_readme_file_bytes_checked_this_run": readme_checked,
        "source_files_sha256_checked_this_run": not test_override,
        "source_posterior_archive_md5_checked_this_run": True,
        "sample_to_actual_historical_runner_execution_attested": False,
        "numeric_posterior_mass_radius_data_revalidated": False,
        "native_photon_likelihood_recomputed": False,
        "EOS_Bayes": "NOT_RUN",
        "note": "A strong publisher-documented file provenance link, not a full 15D inference validation.",
    }