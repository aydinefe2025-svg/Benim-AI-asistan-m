"""Deterministic fault injection for virtual robot task resilience."""
from .shared_world import run_shared_world

def resilience_trial(*, steps=20, energy=100, materials=20, outage_ticks=(3, 4)):
    if not isinstance(steps, int) or not 0 <= steps <= 10000:
        raise ValueError("Invalid steps")
    outages = set(outage_ticks)
    if any(not isinstance(t, int) or t < 1 for t in outages):
        raise ValueError("Outage ticks must be positive integers")
    base = run_shared_world(steps=steps, energy=energy, materials=materials)
    # An outage suppresses successful route completions, without refunding
    # energy already consumed. This is an outcome overlay, not a rerun.
    history = []
    failures = 0
    recovered = 0
    had_outage = False
    for record in base["history"]:
        tick = record["tick"]
        blocked = tick in outages
        success = bool(record["route_success"]) and not blocked
        if blocked and record["route_success"]:
            failures += 1
            had_outage = True
        if had_outage and not blocked and success:
            recovered += 1
            had_outage = False
        history.append({"tick": tick, "outage": blocked, "route_success": success})
    return {"history": history, "failures_injected": failures,
            "recoveries_observed": recovered,
            "successful_routes_after_faults": sum(row["route_success"] for row in history),
            "baseline_successful_routes": base["successful_routes"],
            "note": "Outcome-only fault overlay; resource use is unchanged from baseline."}
