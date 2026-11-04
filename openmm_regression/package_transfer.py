"""Split, verify, or reassemble an OpenMM recovery ZIP for large-file transfer."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def verify_parts(folder: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total_size = 0
    for entry in manifest["parts"]:
        path = folder / entry["name"]
        size, digest = hash_file(path)
        if size != entry["size"] or digest != entry["sha256"]:
            raise ValueError(f"Part verification failed: {path}")
        total_size += size
    if total_size != manifest["archive_size"]:
        raise ValueError("Part sizes do not match the original archive size")
    return manifest


def join_parts(folder: Path, manifest_path: Path, destination: Path) -> None:
    manifest = verify_parts(folder, manifest_path)
    destination = destination.resolve()
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            for entry in manifest["parts"]:
                with (folder / entry["name"]).open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(block)
                        digest.update(block)
                        size += len(block)
        if size != manifest["archive_size"] or digest.hexdigest() != manifest["archive_sha256"]:
            raise ValueError("Reassembled archive does not match the original size and SHA-256")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Original recovery ZIP to split")
    parser.add_argument("--output-dir", type=Path, help="Directory for parts and manifest")
    parser.add_argument("--chunk-mib", type=int, default=50)
    parser.add_argument("--verify-dir", type=Path, help="Verify all parts in this directory")
    parser.add_argument("--join-dir", type=Path, help="Reassemble parts from this directory")
    parser.add_argument("--manifest", type=Path, help="Parts JSON manifest (defaults inside the parts directory)")
    parser.add_argument("--destination", type=Path, help="Output ZIP path used with --join-dir")
    args = parser.parse_args()

    if args.verify_dir or args.join_dir:
        folder = (args.join_dir or args.verify_dir).resolve()
        manifest_path = args.manifest or folder / "openmm-recovery.parts.json"
        manifest = verify_parts(folder, manifest_path)
        if args.join_dir:
            if not args.destination:
                parser.error("--destination is required with --join-dir")
            join_parts(folder, manifest_path, args.destination)
            print(f"PASS: reassembled {manifest['archive_size']} bytes; SHA-256 {manifest['archive_sha256']}")
        else:
            print(f"PASS: verified {len(manifest['parts'])} parts; original SHA-256 {manifest['archive_sha256']}")
        return

    if not args.source:
        parser.error("--source is required when creating parts")
    if args.chunk_mib < 1:
        parser.error("--chunk-mib must be at least 1")
    source = args.source.resolve()
    folder = (args.output_dir or source.parent / "openmm-recovery.parts").resolve()
    folder.mkdir(parents=True, exist_ok=True)
    archive_size, archive_sha = hash_file(source)
    chunk_size = args.chunk_mib * 1024 * 1024
    entries = []
    with source.open("rb") as stream:
        index = 1
        while block := stream.read(chunk_size):
            name = f"openmm-recovery.zip.part{index:03d}"
            target = folder / name
            target.write_bytes(block)
            entries.append({"name": name, "size": len(block), "sha256": hashlib.sha256(block).hexdigest()})
            index += 1
    manifest = {"format": 1, "archive_name": source.name, "archive_size": archive_size,
                "archive_sha256": archive_sha, "chunk_size": chunk_size, "parts": entries}
    manifest_path = folder / "openmm-recovery.parts.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    verify_parts(folder, manifest_path)
    print(f"PASS: split and verified {len(entries)} parts ({archive_size} bytes)")
    print(f"Original SHA-256: {archive_sha}")
    print(f"Parts: {folder}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
