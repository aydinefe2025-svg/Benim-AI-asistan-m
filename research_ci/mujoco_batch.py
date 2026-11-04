"""Compare MuJoCo 3.17 Batch against serial stepping."""
import json
import math
import time
from pathlib import Path
import mujoco
from mujoco import batch

XML = '<mujoco model="ball"><option timestep="0.001" gravity="0 0 -9.81"/><worldbody><body pos="0 0 2"><freejoint/><geom type="sphere" size="0.05" mass="1"/></body></worldbody></mujoco>'
NSIM = 64
NSTEPS = 100
TOLERANCE = 1e-10

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    serial = [mujoco.MjData(model) for _ in range(NSIM)]
    t0 = time.perf_counter()
    for d in serial:
        mujoco.mj_step(model, d, nstep=NSTEPS)
    serial_seconds = time.perf_counter() - t0
    expected = [d.qpos.copy() for d in serial]
    trials = []
    for nthread in (1, 2, 4):
        b = batch.Batch(model, nsim=NSIM, nthread=nthread)
        start = time.perf_counter()
        b.step(nstep=NSTEPS)
        seconds = time.perf_counter() - start
        observed = b.bind("qpos")
        errors = [max(abs(float(a)-float(z)) for a,z in zip(observed[i], expected[i])) for i in range(NSIM)]
        max_error = max(errors)
        if not math.isfinite(max_error) or max_error > TOLERANCE:
            raise AssertionError(f"batch mismatch nthread={nthread}: {max_error}")
        trials.append({"nthread": nthread, "seconds": seconds, "max_absolute_qpos_error": max_error})
    result = {"batch_verified": True, "mujoco_version": mujoco.__version__, "nsim": NSIM, "nsteps": NSTEPS, "serial_seconds": serial_seconds, "tolerance": TOLERANCE, "batch_trials": trials, "note": "Single-run timings; not a reliable speedup benchmark."}
    Path("mujoco_batch_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
