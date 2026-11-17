"""Offline integrity checks for the pinned JESTER APR4 producer lineage."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "J0740_JESTER_APR4_LALSUITE_PROVENANCE_20261117.json"
TEST_LOG = HERE / "J0740_JESTER_APR4_LALSUITE_PROVENANCE_TESTS_20261117.txt"
MANIFEST = HERE / "J0740_JESTER_APR4_LALSUITE_PROVENANCE_MANIFEST_20261117.json"


def main() -> None:
    doc = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert doc["schema"] == "j0740-jester-apr4-lalsuite-producer-provenance-audit-v1"
    assert doc["upstream"]["commit"] == "e6768650ce992abfd1153a6833857572fe5cd230"
    assert doc["source_artifacts"]["apr4_table"]["bytes"] == 56300
    assert doc["source_artifacts"]["apr4_table"]["sha256"] == (
        "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
    )
    facts = doc["generator_method"]
    assert facts["eos_constructor"] == "lalsimulation.SimNeutronStarEOSByName(eos_name)"
    assert facts["native_queries"][0].endswith("PseudoEnthalpyOfPressureGeometerized")
    assert facts["native_queries"][1].endswith("EnergyDensityOfPressureGeometerized")
    assert facts["baryon_density"] == "n_arr = e_arr / _m_avg_geom"
    assert facts["documented_install_command"] == 'uv pip install -e ".[dev]"'
    assert doc["dependency_lineage"]["pyproject_dev_requirement"] == "lalsuite (unversioned)"
    assert doc["dependency_lineage"]["lockfile_resolution"] == "lalsuite==7.26.4"
    gates = doc["physical_gates"]
    assert gates["generator_method_and_approximate_n"] == "VERIFIED_FROM_PINNED_SOURCE"
    assert gates["project_lock_resolution"] == "VERIFIED_7_26_4"
    assert gates["exact_npz_producer_binary"] == "NOT_ESTABLISHED"
    assert gates["apr4_p0_crust_and_absolute_baryon_normalization"] == "NOT_ESTABLISHED"
    assert gates["eos_bayes"] == "NOT_RUN"
    summary = {"status": "PASS", "checks": 16,
               "evidence_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
               "evidence_bytes": EVIDENCE.stat().st_size}
    log = json.dumps(summary, sort_keys=True) + "\n"
    TEST_LOG.write_text(log, encoding="utf-8", newline="\n")
    manifest = {
        "schema": "j0740-apr4-provenance-manifest-v1",
        "result": "PASS",
        "checks": 16,
        "files": {},
    }
    for path in (Path(__file__).resolve(), EVIDENCE, TEST_LOG):
        raw = path.read_bytes()
        manifest["files"][path.name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    print(log, end="")


if __name__ == "__main__":
    main()
