"""Headless, deterministic MuJoCo gravity smoke test; no app secrets required."""
import json
import math
import platform
from pathlib import Path
import mujoco

XML = """
<mujoco model="falling_ball">
  <option timestep="0.001" gravity="0 0 -9.81"/>
  <worldbody>
    <body name="ball" pos="0 0 2">
      <freejoint/>
      <geom type="sphere" size="0.05" mass="1"/>
    </body>
  </worldbody>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    initial = float(data.qpos[2])
    steps = 1000
    for _ in range(steps):
        mujoco.mj_step(model, data)
    elapsed = float(data.time)
    observed = float(data.qpos[2])
    expected = initial - 0.5 * 9.81 * elapsed**2
    error = abs(observed - expected)
    assert math.isfinite(observed)
    assert error < 0.02, (observed, expected, error)
    result = {"physics_verified": True, "engine": "mujoco", "version": mujoco.__version__, "python": platform.python_version(), "steps": steps, "time": elapsed, "observed_z": observed, "analytic_z": expected, "absolute_error": error, "tolerance": 0.02}
    Path("mujoco_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
