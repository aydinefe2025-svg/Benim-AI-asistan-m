"""Repeated MuJoCo batch benchmark with warmup and median timing.

Runs independent simulations with identical initial states. Does not assert
parallel speedup because CI machines are shared and performance fluctuates.
"""
import json
import math
import statistics
import time
from pathlib import Path

import mujoco
from mujoco import batch

XML = '<mujoco model="ball"><option timestep="0.001" gravity="0 0 -9.81"/><worldbody><body pos="0 0 2"><freejoint/><geom type="sphere" size="0.05" mass="1"/></body></worldbody></mujoco>'
NSIM, NSTEPS, REPEATS = 64, 100, 7
TOLERANCE = 1e-10

def serial_trial(model):
    datas = [mujoco.MjData(model) for _ in range(NSIM)]
    start = time.perf_counter()
    for data in datas:
        mujoco.mj_step(model, data, nstep=NSTEPS)
    elapsed = time.perf_counter() - start
    return elapsed, [d.qpos.copy() for d in datas]

def batch_trial(model, threads):
    engine = batch.Batch(model, nsim=NSIM, nthread=threads)
    start = time.perf_counter()
    engine.step(nstep=NSTEPS)
    elapsed = time.perf_counter() - start
    states = engine.bind("qpos")
    return elapsed, [states[i].copy() for i in range(NSIM)]

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    _, expected = serial_trial(model)
    series = {}
    for label, runner in [("serial", lambda: serial_trial(model))] + [
        (f"batch_{threads}", lambda threads=threads: batch_trial(model, threads))
        for threads in (1, 2, 4)
    ]:
        runner()  # warmup
        times = []
        for _ in range(REPEATS):
            elapsed, states = runner()
            max_error = max(
                max(abs(float(a) - float(b)) for a, b in zip(actual, reference))
                for actual, reference in zip(states, expected)
            )
            assert math.isfinite(max_error) and max_error <= TOLERANCE, (label, max_error)
            times.append(elapsed)
        series[label] = {
            "seconds": times,
            "median_seconds": statistics.median(times),
            "min_seconds": min(times),
            "max_seconds": max(times),
            "max_absolute_qpos_error": max_error,
        }
    result = {
        "verified": True,
        "engine_version": mujoco.__version__,
        "simulations": NSIM,
        "steps_per_simulation": NSTEPS,
        "repeats": REPEATS,
        "warmup_per_mode": 1,
        "tolerance": TOLERANCE,
        "results": series,
        "caveat": "Shared CI hardware; single model; timing is descriptive, not a general speedup guarantee.",
    }
    Path("mujoco_benchmark_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
