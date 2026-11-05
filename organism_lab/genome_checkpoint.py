"""Tamper-evident, replay-verifiable digital genome checkpoints.

This preserves *simulated* world state across separate Python processes.
Only a single writer per checkpoint is supported; no daemon is started.
"""
import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .digital_vm import GenomeWorld
from .audit_store import _exclusive_lock

MAX_TICKS = 10000


def _serialize(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _snapshot(world):
    return {
        "metrics": world.metrics(),
        "next_id": world.next_id,
        "organisms": [{**asdict(agent), "genome": list(agent.genome)} for agent in world.organisms],
    }


def _replay(parameters, ticks):
    if type(ticks) is not int or not 0 <= ticks <= MAX_TICKS:
        raise ValueError("Invalid checkpoint tick")
    if not isinstance(parameters, dict) or set(parameters) != {
        "seed", "capacity", "resources_per_tick", "mutation_rate", "allow_replication"
    }:
        raise ValueError("Incorrect checkpoint parameters")
    if type(parameters["resources_per_tick"]) is not int or parameters["resources_per_tick"] > 100000:
        raise ValueError("Resources exceed bounded replay budget")
    world = GenomeWorld(**parameters)
    for _ in range(ticks):
        world.step()
    return world


def _write(path, parameters, ticks, world):
    body = {
        "schema": "genome-replay-checkpoint-v1",
        "parameters": parameters,
        "ticks": ticks,
        "state": _snapshot(world),
    }
    data = {**body, "sha256": hashlib.sha256(_serialize(body)).hexdigest()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".genome-checkpoint-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_serialize(data))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return data


def read_checkpoint(path):
    """Recompute the whole saved experiment and compare full organism state."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict) or set(document) != {
        "schema", "parameters", "ticks", "state", "sha256"
    } or document["schema"] != "genome-replay-checkpoint-v1":
        raise ValueError("Invalid checkpoint schema")
    body = {k: document[k] for k in ("schema", "parameters", "ticks", "state")}
    if hashlib.sha256(_serialize(body)).hexdigest() != document["sha256"]:
        raise ValueError("Checkpoint hash mismatch")
    world = _replay(document["parameters"], document["ticks"])
    if _snapshot(world) != document["state"]:
        raise ValueError("Checkpoint state differs from deterministic replay")
    return document


def initialize_checkpoint(path, *, seed=0, capacity=64, resources_per_tick=10,
                          mutation_rate=0.02, allow_replication=True, target_tick=0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The same lock guards read/check/write across processes on Linux/Windows.
    # Without it two concurrent initializers could both pass exists().
    with _exclusive_lock(path):
        if path.exists():
            raise FileExistsError("Refusing to overwrite an existing checkpoint")
        parameters = dict(seed=seed, capacity=capacity, resources_per_tick=resources_per_tick,
                          mutation_rate=mutation_rate, allow_replication=allow_replication)
        world = _replay(parameters, target_tick)
        result = _write(path, parameters, target_tick, world)
        read_checkpoint(path)
        return result


def advance_checkpoint(path, *, target_tick):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Lock the entire read -> validate -> replay -> atomic replace transaction.
    # Concurrent writers cannot silently overwrite a newer tick.
    with _exclusive_lock(path):
        document = read_checkpoint(path)
        if type(target_tick) is not int or target_tick < document["ticks"] or target_tick > MAX_TICKS:
            raise ValueError("Checkpoint cannot move backwards or exceed bounded steps")
        if target_tick == document["ticks"]:
            return document  # Idempotent: repeat request causes no new write.
        world = _replay(document["parameters"], target_tick)
        result = _write(path, document["parameters"], target_tick, world)
        read_checkpoint(path)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "advance", "verify"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--target-tick", type=int, default=0)
    args = parser.parse_args()
    if args.action == "init":
        doc = initialize_checkpoint(args.file, seed=args.seed, target_tick=args.target_tick)
    elif args.action == "advance":
        doc = advance_checkpoint(args.file, target_tick=args.target_tick)
    else:
        doc = read_checkpoint(args.file)
    print(json.dumps({"verified": True, "ticks": doc["ticks"],
                      "population": doc["state"]["metrics"]["population"],
                      "sha256": doc["sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
