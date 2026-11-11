"""Reproducible CANO seed lab demonstration (no real harvesting/network)."""
import json
from core.seed_ecosystem import SeedEcosystem


def scenario(profile: str) -> dict:
    lab = SeedEcosystem(capacity=10, energy_cap=12, max_generation=8)
    log = []
    solar_schedule = ((9, 9, 9, 0, 0, 0, 9, 8) if profile == "solar_equal_energy"
                      else (4, 4, 4, 0, 0, 0, 4, 4))
    for tick, sun in enumerate(solar_schedule, start=1):
        if tick == 4:
            lab.fail_nodes((1,), authorized=True)  # founder disappears, descendants remain
        sources = {"solar": sun}
        if profile == "diversified":
            sources.update({"water": 2, "thermal": 1})
        log.append(lab.step(sources, authorized=True))
    saved = lab.checkpoint()
    restored = SeedEcosystem.from_checkpoint(json.loads(json.dumps(saved)))
    return {
        "scenario": profile,
        "population": lab.population_size,
        "births": lab.total_births,
        "dormant_ticks": lab.dormant_ticks,
        "harvested_units": lab.total_harvested,
        "energy_spilled_units": lab.discarded_energy,
        "max_generation": max((n.generation for n in lab.nodes.values()), default=None),
        "founder_present": 1 in lab.nodes,
        "sha256": saved["sha256"],
        "readback_match": saved == restored.checkpoint(),
        "timeline": log,
    }


if __name__ == "__main__":
    print(json.dumps({"simulation_only": True, "energy_units": "hypothetical credits",
                      "solar_only": scenario("solar_only"), "solar_equal_energy": scenario("solar_equal_energy"),
                      "diversified": scenario("diversified")},
                     ensure_ascii=False, indent=2))
