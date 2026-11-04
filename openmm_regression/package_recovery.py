"""Build or verify an offline Python 3.12 + OpenMM recovery bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(bundle: Path) -> dict:
    with ZipFile(bundle) as archive:
        try:
            manifest = json.loads(archive.read("recovery_manifest.json"))
        except (KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Recovery bundle has no valid recovery_manifest.json") from exc
        entries = set(archive.namelist())
        expected = set(manifest["files"])
        if entries != expected | {"recovery_manifest.json"}:
            raise ValueError("Recovery bundle contents differ from its manifest")
        for name, record in manifest["files"].items():
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
                    size += len(block)
            if digest.hexdigest() != record["sha256"] or size != record["size"]:
                raise ValueError(f"Recovery bundle verification failed: {name}")
    return manifest


def verify_extracted(bundle: Path, destination: Path) -> dict:
    manifest = verify(bundle)
    destination = destination.resolve()
    for name, record in manifest["files"].items():
        path = destination.joinpath(*Path(name).parts)
        if not path.is_file() or path.stat().st_size != record["size"] or sha256(path) != record["sha256"]:
            raise ValueError(f"Extracted recovery file verification failed: {path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--verify", type=Path, help="Verify an existing ZIP without rebuilding it")
    parser.add_argument("--verify-extracted", type=Path, help="Also verify an already extracted bundle at this directory")
    parser.add_argument("--sha256-file", type=Path, help="Compare the archive with a trusted SHA-256 sidecar")
    parser.add_argument("--output", type=Path, help="Output ZIP; defaults to workspace/openmm-recovery.zip")
    args = parser.parse_args()

    if args.verify:
        if args.sha256_file:
            expected = args.sha256_file.read_text(encoding="ascii").split()[0].lower()
            actual = sha256(args.verify)
            if actual != expected:
                raise ValueError(f"Archive SHA-256 mismatch: expected {expected}, got {actual}")
        manifest = verify_extracted(args.verify, args.verify_extracted) if args.verify_extracted else verify(args.verify)
        target = f" and extracted tree {args.verify_extracted}" if args.verify_extracted else ""
        checksum = " and trusted SHA-256" if args.sha256_file else ""
        print(f"PASS: verified {len(manifest['files'])} files{checksum} in {args.verify}{target} ({args.verify.stat().st_size} bytes)")
        return
    if args.verify_extracted or args.sha256_file:
        parser.error("--verify-extracted and --sha256-file require --verify")

    workspace = args.workspace.resolve()
    runtime = workspace / ".runtime312"
    dist = workspace / "dist"
    if not (runtime / "python.exe").is_file():
        raise FileNotFoundError(f"CPython runtime not found: {runtime / 'python.exe'}")
    wheels = sorted(path for path in dist.glob("*.whl") if path.is_file())
    if not wheels:
        raise FileNotFoundError(f"No offline wheels found in {dist}")

    source_files = [(path, path.relative_to(workspace).as_posix()) for path in runtime.rglob("*") if path.is_file()]
    source_files.extend((path, path.relative_to(workspace).as_posix()) for path in wheels)
    records = {
        name: {"size": path.stat().st_size, "sha256": sha256(path)}
        for path, name in source_files
    }
    manifest = {"format": 1, "python": "3.12", "files": records}
    output = (args.output or workspace / "openmm-recovery.zip").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        with ZipFile(temporary, "w", allowZip64=True) as archive:
            for path, name in source_files:
                compression = ZIP_STORED if path.suffix == ".whl" else ZIP_DEFLATED
                archive.write(path, name, compress_type=compression, compresslevel=6 if compression == ZIP_DEFLATED else None)
            archive.writestr("recovery_manifest.json", json.dumps(manifest, indent=2) + "\n", compress_type=ZIP_DEFLATED)
        verify(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    digest = sha256(output)
    sidecar = output.with_suffix(output.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"PASS: packaged and verified {len(source_files)} files ({output.stat().st_size} bytes)")
    print(f"SHA-256: {digest}")
    print(f"Bundle: {output}")
    print(f"Checksum: {sidecar}")


if __name__ == "__main__":
    main()
