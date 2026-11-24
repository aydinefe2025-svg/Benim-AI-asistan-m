#!/usr/bin/env python3
"""Map the original HPC-only X-PSI argument paths to verified staged inputs."""
import argparse
import json
from pathlib import Path


def remap(config: Path, root: Path, output: Path, receipt: Path):
    if not config.is_file() or not root.is_dir():
        raise FileNotFoundError("Original configuration or staged input root missing")
    by_name = {}
    for path in root.rglob("*"):
        if path.is_file():
            by_name.setdefault(path.name, []).append(path)
    rows = []
    lines = []
    skipped = []
    for raw in config.read_text().splitlines():
        line = raw.strip()
        if line in {"--multinest", "--emcee", "--resume"}:
            skipped.append(line)
            continue
        if "-path=" not in line:
            lines.append(raw)
            continue
        key, old = line.split("=", 1)
        basename = Path(old).name
        matches = by_name.get(basename, [])
        generated = key == "--NICER-matrix-path" and not matches
        if generated:
            new = root / "J0740_products" / "W23" / basename
            if not new.parent.is_dir():
                raise FileNotFoundError(new.parent)
        elif len(matches) == 1:
            new = matches[0]
        else:
            raise ValueError("Input path has %d matches: %s" % (len(matches), key))
        lines.append(key + "=" + str(new.resolve()))
        rows.append({"argument": key, "original": old,
                     "staged": str(new.resolve()), "generated_from_events": generated,
                     "size_bytes": None if generated else new.stat().st_size})
    if len(rows) != 21 or sum(row["generated_from_events"] for row in rows) != 1:
        raise ValueError("Unexpected original config input coverage")
    if "--NICER" not in lines or "--XMM" not in lines:
        raise ValueError("Original NICER+XMM flags absent")
    output.write_text("\n".join(lines) + "\n")
    result = {"status": "PASS_20_ORIGINAL_INPUTS_AND_ONE_EVENT_BIN_MATRIX",
              "original_config": str(config), "remapped_config": str(output),
              "paths": rows, "disabled_sampling_flags_for_one_point_check": skipped}
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(result["status"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    a = p.parse_args()
    remap(a.config, a.root, a.output, a.receipt)
