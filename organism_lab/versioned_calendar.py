"""Opt-in, bounded v1 -> v2 digital-simulation checkpoint/calendar bridge.

Does not modify the existing v1 calendar, watchdog, or schedule.  The v1
checkpoint is preserved, byte-for-byte as an embedded immutable anchor.
A migration requires the caller-supplied canonical anchor digest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .audit_store import _exclusive_lock
from .calendar_cycle import _atomic_bytes, _day_and_tick, _report_for_day, SCHEMA as DAILY_V1
from .digital_vm import DigitalOrganism, execute_genome
from .genome_checkpoint import _replay, _snapshot, _serialize, read_checkpoint, MAX_TICKS

V1 = "genome-replay-checkpoint-v1"
V2 = "genome-replay-checkpoint-v2"
POLICY = "maintenance-first-budget-v1"
DAILY_V2 = "cano-calendar-digital-cycle-v2"
INTERPRETATION = (
    "Deterministic offline digital-organism simulation; births are not proof "
    "of learning, living cells, or physical self-replication."
)


def _hash(body):
    return hashlib.sha256(_serialize(body)).hexdigest()


def _signed(body):
    return {**body, "sha256": _hash(body)}


def _original_anchor(anchor):
    if not isinstance(anchor, dict) or set(anchor) != {"schema", "parameters", "ticks", "state", "sha256"}:
        raise ValueError("Incorrect v1 anchor schema")
    if anchor["schema"] != V1:
        raise ValueError("Non-v1 anchor rejected")
    body = {key: anchor[key] for key in ("schema", "parameters", "ticks", "state")}
    if anchor["sha256"] != _hash(body):
        raise ValueError("v1 anchor checksum mismatch")
    if type(anchor["ticks"]) is not int or not 0 <= anchor["ticks"] <= MAX_TICKS:
        raise ValueError("v1 anchor tick out of budget")
    old = _replay(anchor["parameters"], anchor["ticks"])
    if _snapshot(old) != anchor["state"]:
        raise ValueError("v1 anchor fails independent replay")
    return old


def _maintenance_step(world):
    """Same resource input; prioritize survival, then smallest energy; finite cap.

    This is an experimental policy, not biological survival or autonomous learning.
    """
    world.tick += 1
    ordered = sorted(world.organisms, key=lambda agent: agent.identifier)
    available = world.resources_per_tick
    allocation = {agent.identifier: 0 for agent in ordered}
    for _ in range(2):
        for agent in sorted(ordered, key=lambda agent: (agent.energy, agent.identifier)):
            if available:
                allocation[agent.identifier] += 1
                available -= 1
    survivors = []
    for agent in ordered:
        energy = agent.energy - 1 + allocation[agent.identifier]
        if energy > 0:
            survivors.append(DigitalOrganism(agent.identifier, agent.parent,
                                              agent.generation, energy, agent.genome))
        else:
            world.deaths += 1
    children = []
    parents = []
    limit = min(world.capacity, world.resources_per_tick)
    for agent in survivors:
        genome = execute_genome(agent.genome) if world.allow_replication else None
        if genome is not None and agent.energy >= 8 and len(survivors) + len(children) < limit:
            child = DigitalOrganism(world.next_id, agent.identifier,
                                    agent.generation + 1, 3, world._mutate(genome))
            children.append(child)
            world.births += 1
            world.next_id += 1
            agent = DigitalOrganism(agent.identifier, agent.parent,
                                    agent.generation, agent.energy - 4, agent.genome)
        parents.append(agent)
    world.organisms = parents + children
    assert world.births - world.deaths + 1 == len(world.organisms)
    assert len(world.organisms) <= world.capacity


def _replayed(anchor, target_tick, *, division_disabled=False):
    _original_anchor(anchor)
    if type(target_tick) is not int or not anchor["ticks"] <= target_tick <= MAX_TICKS:
        raise ValueError("Invalid target tick for anchored transition")
    params = dict(anchor["parameters"])
    if division_disabled:
        params["allow_replication"] = False
    world = _replay(params, anchor["ticks"])
    for _ in range(target_tick - anchor["ticks"]):
        _maintenance_step(world)
    return world


def _construct(anchor, target_tick):
    state = _snapshot(_replayed(anchor, target_tick))
    return _signed({"schema": V2, "policy": POLICY, "anchor": anchor,
                    "ticks": target_tick, "state": state})


def inspect_checkpoint(path):
    """Verify v1 original or fully replay-validated v2; never write."""
    document = json.loads(Path(path).read_bytes())
    if not isinstance(document, dict):
        raise ValueError("Checkpoint must be an object")
    if document.get("schema") == V1:
        # Preserve the existing repository's authoritative v1 reader.
        return read_checkpoint(path)
    if document.get("schema") != V2 or set(document) != {
        "schema", "policy", "anchor", "ticks", "state", "sha256"
    }:
        raise ValueError("Unknown checkpoint format")
    if document["policy"] != POLICY:
        raise ValueError("Policy mismatch")
    if _hash({key: value for key, value in document.items() if key != "sha256"}) != document["sha256"]:
        raise ValueError("v2 checksum mismatch")
    if _construct(document["anchor"], document["ticks"]) != document:
        raise ValueError("v2 deterministic replay mismatch")
    return document


def _save_checkpoint(path, doc):
    path = Path(path)
    _atomic_bytes(path, _serialize(doc))
    if inspect_checkpoint(path) != doc:
        raise ValueError("Checkpoint independent readback failed")
    return doc


def migrate_checkpoint(path, *, expected_anchor_sha):
    """Only explicit, pinned migration can alter the checkpoint file."""
    path = Path(path)
    with _exclusive_lock(path):
        existing = inspect_checkpoint(path)
        anchor = existing["anchor"] if existing["schema"] == V2 else existing
        if not isinstance(expected_anchor_sha, str) or len(expected_anchor_sha) != 64:
            raise ValueError("Expected anchor sha256 required")
        if anchor["sha256"] != expected_anchor_sha:
            raise ValueError("Pinned anchor SHA mismatch; no write")
        if existing["schema"] == V2:
            return existing
        return _save_checkpoint(path, _construct(anchor, existing["ticks"]))


def advance_checkpoint_v2(path, *, target_tick):
    path = Path(path)
    with _exclusive_lock(path):
        current = inspect_checkpoint(path)
        if current["schema"] != V2:
            raise ValueError("Explicit pinned migration must happen first")
        if type(target_tick) is not int or not current["ticks"] <= target_tick <= MAX_TICKS:
            raise ValueError("Cannot rewind or exceed bounded replay")
        if current["ticks"] == target_tick:
            return current
        return _save_checkpoint(path, _construct(current["anchor"], target_tick))


def _report_v2(anchor, *, day):
    _, tick = _day_and_tick(day)
    if tick <= anchor["ticks"]:
        raise ValueError("V1 historical day is not an experimental V2 day")
    experimental = _replayed(anchor, tick)
    control = _replayed(anchor, tick, division_disabled=True)
    body = {
        "schema": DAILY_V2, "day": day, "tick": tick,
        "parameters": anchor["parameters"],
        "policy": POLICY, "anchor_sha256": anchor["sha256"],
        "transition_tick": anchor["ticks"],
        "observed": experimental.metrics(),
        "division_disabled_control": control.metrics(),
        "state_sha256": _hash(_snapshot(experimental)),
        "interpretation": INTERPRETATION,
    }
    return _signed(body)


def inspect_day_v2(root, *, day):
    """Read-only same-day watchdog; checks v1 history separately."""
    root = Path(root)
    current = inspect_checkpoint(root / "genome-state.json")
    if current["schema"] != V2:
        raise ValueError("V2 checkpoint required")
    _, expected_tick = _day_and_tick(day)
    if expected_tick != current["ticks"]:
        raise ValueError("Stale or future V2 checkpoint")
    expected = _report_v2(current["anchor"], day=day)
    report = json.loads((root / "daily" / f"{day}.json").read_bytes())
    if report != expected or _hash(current["state"]) != report["state_sha256"]:
        raise ValueError("Daily V2 report does not match deterministic replay")
    if report["division_disabled_control"]["births"] != 0:
        raise ValueError("Division-disabled negative control failed")
    return {"status": "verified", "day": day, "tick": expected_tick,
            "population": report["observed"]["population"],
            "births": report["observed"]["births"],
            "control_births": 0, "state_sha256": current["sha256"],
            "daily_sha256": report["sha256"]}


def run_day_v2(root, *, day, expected_anchor_sha):
    """Opt-in, cross-process locked calendar transition with atomic daily writes."""
    _, tick = _day_and_tick(day)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "genome-state.json"
    report_file = root / "daily" / f"{day}.json"
    with _exclusive_lock(root / "calendar-cycle"):
        current = inspect_checkpoint(checkpoint)
        anchor = current["anchor"] if current["schema"] == V2 else current
        if anchor["sha256"] != expected_anchor_sha:
            raise ValueError("Explicit pinned V1 anchor required")
        if tick <= anchor["ticks"]:
            raise ValueError("Refusing to rewrite historical V1 day")
        expected = _report_v2(anchor, day=day)
        # Check for conflicting reports BEFORE migration or advancing state.
        if report_file.exists():
            if json.loads(report_file.read_bytes()) != expected:
                raise ValueError("Existing report mismatch; no write")
        if current["schema"] == V1:
            current = migrate_checkpoint(checkpoint, expected_anchor_sha=expected_anchor_sha)
        if current["ticks"] < tick:
            advance_checkpoint_v2(checkpoint, target_tick=tick)
        if not report_file.exists():
            report_file.parent.mkdir(parents=True, exist_ok=True)
            _atomic_bytes(report_file, _serialize(expected))
        if json.loads(report_file.read_bytes()) != expected:
            raise ValueError("V2 report readback failed")
        # Exact current target for watchdog; later historical reruns can validate
        # previously persisted reports without rewriting any checkpoint.
        if inspect_checkpoint(checkpoint)["ticks"] == tick:
            inspect_day_v2(root, day=day)
        return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("migrate", "advance", "run-day", "inspect-day", "inspect"))
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--day")
    parser.add_argument("--target-tick", type=int)
    parser.add_argument("--expected-anchor-sha")
    args = parser.parse_args(argv)
    state = args.state_dir / "genome-state.json"
    if args.action == "migrate":
        doc = migrate_checkpoint(state, expected_anchor_sha=args.expected_anchor_sha)
    elif args.action == "advance":
        doc = advance_checkpoint_v2(state, target_tick=args.target_tick)
    elif args.action == "run-day":
        doc = run_day_v2(args.state_dir, day=args.day, expected_anchor_sha=args.expected_anchor_sha)
    elif args.action == "inspect-day":
        doc = inspect_day_v2(args.state_dir, day=args.day)
    else:
        doc = inspect_checkpoint(state)
    print(json.dumps(doc, sort_keys=True))


if __name__ == "__main__":
    main()
