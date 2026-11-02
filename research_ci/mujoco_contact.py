"""Validate a contact-rich MuJoCo scene independently of free-fall tests."""
import json
import math
from pathlib import Path
import mujoco

XML = """
<mujoco model="contact_validation">
  <option timestep="0.001" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="2 2 0.1"/>
    <body name="ball" pos="0 0 1">
      <freejoint/>
      <geom name="ball_geom" type="sphere" size="0.1" mass="1"/>
    </body>
  </worldbody>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    initial_z = float(data.qpos[2])
    contact_steps = 0
    minimum_z = initial_z
    for _ in range(3000):
        mujoco.mj_step(model, data)
        contact_steps += int(data.ncon > 0)
        minimum_z = min(minimum_z, float(data.qpos[2]))
    final_z = float(data.qpos[2])
    assert contact_steps > 0, "No contacts detected"
    assert math.isfinite(final_z), "Nonfinite final state"
    assert abs(final_z - 0.1) < 0.03, ("Sphere failed to settle near plane", final_z)
    assert minimum_z > -0.05, ("Sphere penetrated plane excessively", minimum_z)
    result = {
        "contact_verified": True,
        "engine": mujoco.__version__,
        "steps": 3000,
        "contact_steps": contact_steps,
        "initial_z": initial_z,
        "final_z": final_z,
        "minimum_z": minimum_z,
        "expected_rest_z": 0.1,
        "settling_tolerance": 0.03,
    }
    Path("mujoco_contact_result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
