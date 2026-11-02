"""MuJoCo motor-driven hinge validation with limit and tracking checks."""
import json
import math
from pathlib import Path
import mujoco

XML = """
<mujoco model="actuated_hinge">
  <option timestep="0.002" gravity="0 0 0"/>
  <worldbody>
    <body name="arm">
      <joint name="hinge" type="hinge" axis="0 0 1" range="-45 45" limited="true" damping="1"/>
      <geom type="capsule" fromto="0 0 0 1 0 0" size="0.04" mass="1"/>
    </body>
  </worldbody>
  <actuator>
    <position name="target" joint="hinge" kp="30" kv="8" ctrlrange="-0.5 0.5" ctrllimited="true"/>
  </actuator>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    target = 0.4
    data.ctrl[0] = target
    positions = []
    for _ in range(2000):
        mujoco.mj_step(model, data)
        angle = float(data.qpos[0])
        assert math.isfinite(angle), "Non-finite joint position"
        assert abs(angle) <= math.pi / 4 + 0.02, "Joint exceeded limit"
        positions.append(angle)
    final_angle = positions[-1]
    final_velocity = float(data.qvel[0])
    assert abs(final_angle - target) < 0.03, (final_angle, target)
    assert abs(final_velocity) < 0.03, final_velocity
    assert max(positions) > 0.2, "Actuator did not move the joint"
    result = {
        "verified": True,
        "engine": mujoco.__version__,
        "steps": 2000,
        "target_radians": target,
        "final_radians": final_angle,
        "final_velocity_radians_per_second": final_velocity,
        "minimum_radians": min(positions),
        "maximum_radians": max(positions),
        "limit_radians": math.pi / 4,
        "position_tolerance": 0.03,
        "velocity_tolerance": 0.03
    }
    Path("mujoco_actuator_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
