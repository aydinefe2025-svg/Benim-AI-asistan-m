#!/usr/bin/env python3
"""Extract original photon inputs in a single partial Zenodo tar stream.

This is an input staging preflight, not a photon likelihood. F144 verifies the
published MD5 of the entire compressed archive independently.
"""
import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = "J0740_GAMMA_zenodo/"
SOURCE = ROOT + "STU/STU_NICER_XMM_hr/STU_modules/"
RUN = ROOT + "STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/"
EXPECTED = {
    SOURCE + "config.ini": "02592091e8c10d126b10070e0e33515a292d57d750c2a45d624065d056752ede",
    SOURCE + "CustomPrior_GLS_compressed_scaling_Dfix.py": "ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93",
    SOURCE + "main_lp40k_Xse001_Dfix.py": "440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af",
    RUN + "out_": "f20ae7db9550a9fd608542c1b43fc9534a3e396df7ef5c2dad66493793caa2de",
}
DATA = (
    ROOT + "model_data/",
    ROOT + "J0740_products/W23/",
    ROOT + "J0740_products/XMM/",
)
LIMIT = 750_000_000
TOTAL_LIMIT = 3_500_000_000


def stage(output, evidence):
    output.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    found = {}
    total = 0
    modules_started = False
    count = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as tar:
        for member in tar:
            if modules_started and not member.name.startswith(SOURCE):
                break
            if member.name.startswith(SOURCE):
                modules_started = True
            if not member.isfile():
                continue
            count += 1
            select = (
                member.name.startswith(DATA)
                or member.name in EXPECTED
                or (member.name.startswith(SOURCE)
                    and member.name.endswith((".py", ".ini", ".sh")))
            )
            if not select:
                continue
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or not member.name.startswith(ROOT):
                raise ValueError("Unsafe tar path")
            if member.size > LIMIT or total + member.size > TOTAL_LIMIT:
                raise ValueError("Unexpected source input size: " + member.name)
            target = output.joinpath(*pure.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("Cannot read " + member.name)
            sha = hashlib.sha256()
            n = 0
            with target.open("wb") as dest:
                for chunk in iter(lambda: source.read(1048576), b""):
                    dest.write(chunk)
                    sha.update(chunk)
                    n += len(chunk)
            if n != member.size:
                raise ValueError("Truncated member: " + member.name)
            digest = sha.hexdigest()
            if member.name in EXPECTED and digest != EXPECTED[member.name]:
                raise ValueError("Original source SHA mismatch: " + member.name)
            total += n
            found[member.name] = {"bytes": n, "sha256": digest}
            print("F146_EXTRACTED", member.name, n, flush=True)
    missing = sorted(set(EXPECTED) - set(found))
    if missing or not modules_started:
        raise ValueError("Missing original source inputs: " + repr(missing))
    result = {
        "schema": "J0740_F146_ORIGINAL_PHOTON_INPUTS_V1",
        "archive": "Zenodo 10519473, published MD5 7792c92b9ae1fa404ae5bdd3920ce075",
        "source_expected_sha": EXPECTED,
        "members_before_source_boundary": count,
        "selected_bytes": total,
        "selected_members": found,
        "status": "PASS_ORIGINAL_INPUT_STAGING",
        "limitations": "Partial stream; no full-archive MD5 and no photon likelihood. F144 verifies entire archive separately.",
    }
    (evidence / "input_stage.json").write_text(json.dumps(result, indent=2) + "\n")
    print("F146_INPUT_STAGE_PASS", len(found), total, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args()
    stage(a.output, a.evidence)
