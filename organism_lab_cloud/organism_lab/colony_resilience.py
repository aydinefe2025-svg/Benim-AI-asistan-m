"""Bounded digital study of colony communication and fault containment.

This is an abstract network simulation. It does not control biological agents,
robots, or production security systems and cannot establish real-world safety.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA = "organism-lab-colony-resilience-v1"
MAX_SEEDS = 50
MAX_TICKS = 40
MAX_POPULATION = 32
CONTACT_PROBABILITY = 0.08


def _simulate(seed: int, *, ticks: int, population: int, compartments: int,
              fault_tick: int, protected: bool) -> dict:
    """Simulate a useful protocol spreading before one sender emits a bad packet."""
    rng = random.Random(seed)
    contact_rng = random.Random(seed ^ 0x5EEDC0DE)
    group_size = population // compartments
    groups = [i // group_size for i in range(population)]
    knowledge = [i == 0 for i in range(population)]
    compromised = [False] * population
    faulted_node = rng.randrange(population)
    rejected_packets = 0

    for tick in range(ticks):
        # Draw the same directed contact graph for both paired study arms.
        # Generate it before applying policy filters so both arms see identical contacts.
        contacts = [
            [contact_rng.random() < CONTACT_PROBABILITY for _ in range(population)]
            for _ in range(population)
        ]
        if tick == fault_tick:
            compromised[faulted_node] = True
            knowledge[faulted_node] = False

        previous_knowledge = knowledge[:]
        previous_compromised = compromised[:]
        new_knowledge = knowledge[:]
        new_compromised = compromised[:]

        for receiver in range(population):
            if previous_compromised[receiver]:
                continue
            for sender in range(population):
                if sender == receiver or not contacts[receiver][sender]:
                    continue
                if protected:
                    same_compartment = groups[sender] == groups[receiver]
                    # Cross-compartment traffic uses a narrow, alternate-tick gateway.
                    gateway_open = tick % 2 == 1
                    if not same_compartment and not gateway_open:
                        continue
                    if previous_compromised[sender]:
                        rejected_packets += 1
                        continue
                if previous_compromised[sender]:
                    new_compromised[receiver] = True
                    new_knowledge[receiver] = False
                    break
                if previous_knowledge[sender]:
                    new_knowledge[receiver] = True
        knowledge, compromised = new_knowledge, new_compromised

    healthy_ready = sum(knowledge[i] and not compromised[i] for i in range(population))
    contained_groups = sum(
        all(knowledge[i] and not compromised[i]
            for i in range(population) if groups[i] == group)
        for group in range(compartments)
    )
    return {
        "seed": seed,
        "faulted_node": faulted_node,
        "healthy_ready": healthy_ready,
        "compromised_nodes": sum(compromised),
        "fully_ready_compartments": contained_groups,
        "rejected_bad_packets": rejected_packets,
    }


def _mean(rows: list[dict], key: str) -> float:
    return sum(row[key] for row in rows) / len(rows)


def _report_digest(report: dict) -> str:
    payload = {key: value for key, value in report.items()
               if key not in {"sha256", "generated_at", "run_id"}}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_colony_resilience_report(report: dict) -> bool:
    """Reject malformed or altered report content before display or persistence."""
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        raise ValueError("Unrecognized colony resilience report")
    if report.get("status") != "simulation_only":
        raise ValueError("Colony report status is invalid")
    digest = report.get("sha256")
    if not isinstance(digest, str) or digest != _report_digest(report):
        raise ValueError("Colony resilience report integrity check failed")
    return True


def run_colony_resilience_study(*, seeds=30, ticks=10, population=16,
                                compartments=4, fault_tick=3) -> dict:
    """Compare open broadcast with segmented, allow-listed communication.

    Both arms use paired seeds and the same simulated single-node fault.
    Resource bounds keep this inexpensive enough for an on-demand free service.
    """
    values = (seeds, ticks, population, compartments, fault_tick)
    if any(type(value) is not int for value in values):
        raise ValueError("Study parameters must be integers")
    if not 2 <= seeds <= MAX_SEEDS:
        raise ValueError("Seed count outside the bounded study budget")
    if not 4 <= population <= MAX_POPULATION:
        raise ValueError("Population outside the bounded study budget")
    if not 1 <= compartments <= population or population % compartments:
        raise ValueError("Population must divide evenly into compartments")
    if not 3 <= ticks <= MAX_TICKS or not 1 <= fault_tick < ticks - 1:
        raise ValueError("Invalid tick or fault timing")

    paired_seeds = list(range(seeds))
    open_network = [
        _simulate(seed, ticks=ticks, population=population,
                  compartments=compartments, fault_tick=fault_tick,
                  protected=False)
        for seed in paired_seeds
    ]
    protected_network = [
        _simulate(seed, ticks=ticks, population=population,
                  compartments=compartments, fault_tick=fault_tick,
                  protected=True)
        for seed in paired_seeds
    ]
    report = {
        "schema": SCHEMA,
        "status": "simulation_only",
        "design": {
            "paired_seeds": paired_seeds,
            "ticks": ticks,
            "population": population,
            "compartments": compartments,
            "simulated_fault_tick": fault_tick,
            "directed_contact_probability_per_tick": CONTACT_PROBABILITY,
            "fault_model": "one virtual node begins emitting an invalid message",
        },
        "arms": {
            "open_broadcast": {
                "description": "All nodes share the same randomly sampled directed contacts.",
                "mean_healthy_ready": _mean(open_network, "healthy_ready"),
                "mean_compromised_nodes": _mean(open_network, "compromised_nodes"),
                "mean_fully_ready_compartments": _mean(open_network, "fully_ready_compartments"),
                "trials": open_network,
            },
            "segmented_validated": {
                "description": "The same sampled contacts are filtered by compartment gateways; invalid senders are rejected.",
                "mean_healthy_ready": _mean(protected_network, "healthy_ready"),
                "mean_compromised_nodes": _mean(protected_network, "compromised_nodes"),
                "mean_fully_ready_compartments": _mean(protected_network, "fully_ready_compartments"),
                "mean_rejected_bad_packets": _mean(protected_network, "rejected_bad_packets"),
                "trials": protected_network,
            },
        },
        "interpretation": {
            "summary": "Sonuçlar yalnızca bu basitleştirilmiş ağ simülatörüne aittir.",
            "limits": [
                "Bu bir gerçek siber güvenlik testi veya güvenlik garantisi değildir.",
                "Sanal ajanlar gerçek biyolojik organizmalar veya robotlar değildir.",
                "Sonuçlar seçilen topoloji, doğrulama kuralı ve tek hata senaryosuyla sınırlıdır.",
            ],
        },
    }
    report["sha256"] = _report_digest(report)
    return report



def paired_trial_rows(report: dict) -> list[dict]:
    """Return per-seed arm comparisons after validating the matched experiment."""
    validate_colony_resilience_report(report)
    arms = report["arms"]
    open_trials = arms["open_broadcast"].get("trials")
    protected_trials = arms["segmented_validated"].get("trials")
    if (not isinstance(open_trials, list) or not open_trials
            or not isinstance(protected_trials, list)
            or len(open_trials) != len(protected_trials)):
        raise ValueError("Paired trial lists are incomplete")
    rows = []
    for open_trial, protected_trial in zip(open_trials, protected_trials):
        if (not isinstance(open_trial, dict) or not isinstance(protected_trial, dict)
                or type(open_trial.get("seed")) is not int
                or open_trial.get("seed") != protected_trial.get("seed")
                or type(open_trial.get("faulted_node")) is not int
                or open_trial.get("faulted_node") != protected_trial.get("faulted_node")):
            raise ValueError("Paired trial seed or fault does not match")
        metrics = ("healthy_ready", "compromised_nodes", "fully_ready_compartments")
        if any(type(trial.get(metric)) is not int
               for trial in (open_trial, protected_trial) for metric in metrics):
            raise ValueError("Paired trial metrics are invalid")
        rows.append({
            "Tohum": open_trial["seed"],
            "Arızalı ajan": open_trial["faulted_node"],
            "Açık ağ · hazır": open_trial["healthy_ready"],
            "Bölümlü ağ · hazır": protected_trial["healthy_ready"],
            "Hazır ajan farkı": protected_trial["healthy_ready"] - open_trial["healthy_ready"],
            "Açık ağ · etkilenmiş": open_trial["compromised_nodes"],
            "Bölümlü ağ · etkilenmiş": protected_trial["compromised_nodes"],
            "Etkilenmiş ajan farkı": protected_trial["compromised_nodes"] - open_trial["compromised_nodes"],
            "Açık ağ · hazır bölme": open_trial["fully_ready_compartments"],
            "Bölümlü ağ · hazır bölme": protected_trial["fully_ready_compartments"],
            "Reddedilen hatalı mesaj": protected_trial.get("rejected_bad_packets", 0),
        })
    return rows


def explain_colony_resilience(report: dict) -> str:
    """Make the paired experiment legible without an LLM call."""
    validate_colony_resilience_report(report)
    arms = report.get("arms", {})
    open_arm = arms.get("open_broadcast", {})
    protected = arms.get("segmented_validated", {})
    required = ("mean_healthy_ready", "mean_compromised_nodes",
                "mean_fully_ready_compartments")
    if any(type(arm.get(key)) not in (int, float)
           for arm in (open_arm, protected) for key in required):
        raise ValueError("Incomplete colony resilience report")
    contact_probability = report.get("design", {}).get("directed_contact_probability_per_tick")
    if contact_probability is None:
        # Older archived runs predate the stochastic network and used a complete graph.
        contact_description = (
            "**Eski rapor varsayımı:** Her adımda sanal ajan çiftleri arasında tam bağlantı vardı. "
            "Bu sonucu yeni olasılıksal deneyle doğrudan karşılaştırma."
        )
    elif type(contact_probability) in (int, float) and 0 <= contact_probability <= 1:
        contact_description = (
            f"**Model varsayımı:** Her adımda olası yönlü bağlantıların %{contact_probability * 100:.0f}'i "
            "örneklendi; iki ağ kolu aynı bağlantı örüntülerini kullandı."
        )
    else:
        raise ValueError("Invalid contact probability in report")
    return (
        f"**Ne denendi?** {report['design']['population']} sanal ajanı "
        f"{report['design']['compartments']} bölmeye ayırdık ve aynı "
        f"{len(report['design']['paired_seeds'])} başlangıçta iki iletişim düzenini karşılaştırdık. "
        f"{contact_description} {report['design']['simulated_fault_tick']}. adımda "
        "tek bir sanal ajanın geçersiz mesaj göndermesini modelledik.\n\n"
        f"**Ne ölçtük?** Açık ağda son durumda ortalama "
        f"{open_arm['mean_healthy_ready']:.1f}/{report['design']['population']} ajan hazır, "
        f"{open_arm['mean_compromised_nodes']:.1f} ajan etkilenmişti. Bölümlenmiş ve doğrulanan ağda "
        f"{protected['mean_healthy_ready']:.1f}/{report['design']['population']} ajan hazır, "
        f"{protected['mean_compromised_nodes']:.1f} ajan etkilenmişti; ortalama "
        f"{protected.get('mean_rejected_bad_packets', 0):.1f} geçersiz paket reddedildi.\n\n"
        "**Anlamı:** Bu modelde bölme ve mesaj doğrulama, tek bir sanal arızanın yayılmasını sınırladı. "
        "Bu bir gerçek güvenlik garantisi değildir; gerçek saldırılar, kimlik doğrulama, anahtar yönetimi "
        "ve uygulama kodu ayrıca denetlenmelidir."
    )


def save_colony_resilience_study(report: dict, path) -> dict:
    """Write a versioned result and latest pointer atomically with read-back."""
    explanation = explain_colony_resilience(report)
    if not explanation:
        raise ValueError("Study report failed validation")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid4().hex
    document = {**report, "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id}
    payload = json.dumps(document, sort_keys=True, ensure_ascii=False,
                         indent=2, allow_nan=False) + "\n"
    history = target.parent / "colony-resilience-runs"
    history.mkdir(parents=True, exist_ok=True)

    def write_verified(destination: Path) -> None:
        temporary = destination.with_name(destination.name + f".{uuid4().hex}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(destination)
            restored = json.loads(destination.read_text(encoding="utf-8"))
            validate_colony_resilience_report(restored)
            if restored != document:
                raise OSError("Study result failed read-back verification")
        finally:
            temporary.unlink(missing_ok=True)

    write_verified(history / f"colony-resilience-{run_id}.json")
    write_verified(target)
    return document
