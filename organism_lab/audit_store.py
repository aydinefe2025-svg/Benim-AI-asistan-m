"""Local append-only audit storage for explicitly run simulation tasks.

No network or remote archive writes. Each record has a chained SHA-256 digest.
"""
import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def _exclusive_lock(file):
    """Coordinate concurrent writers on POSIX and Windows using a separate lock file."""
    lock_path = file.with_name(file.name + ".lock")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            lock.write(b"0")
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)



def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def read_audit(path):
    file = Path(path)
    if not file.exists():
        return []
    raw = file.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Incomplete final audit record")
    records = []
    previous = "0" * 64
    for line in file.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        digest = record.get("digest")
        payload = {key: value for key, value in record.items() if key != "digest"}
        if payload.get("previous") != previous or digest != hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest():
            raise ValueError("Audit integrity failure")
        records.append(record)
        previous = digest
    return records


def append_audit(path, result):
    if not isinstance(result, dict) or result.get("status") not in ("verified", "failed"):
        raise ValueError("Only explicit verified/failed task records can be stored")
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(file):
        previous_records = read_audit(file)
        previous = previous_records[-1]["digest"] if previous_records else "0" * 64
        payload = {"previous": previous, "result": result, "status": result["status"]}
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        record = {**payload, "digest": digest}
        with file.open("a", encoding="utf-8") as stream:
            stream.write(_canonical(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return record
