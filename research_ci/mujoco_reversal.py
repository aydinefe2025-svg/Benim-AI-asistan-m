"""Independent MuJoCo actuator reversal and saturation checks."""
import json
import math
from pathlib import Path
import mujoco

XML = """
<mujoco model="reversal">
  <option timestep="0.002" gravity="0 0 0"/>
  <worldbody>
    <body>
      <joint name="hinge" type="hinge" axis="0 0 1" range="-45 45" limited="true" damping="1"/>
      <geom type="capsule" fromto="0 0 0 1 0 0" size="0.04" mass="1"/>
    </body>
  </worldbody>
  <actuator>
    <position joint="hinge" kp="30" kv="8" ctrlrange="-0.5 0.5" ctrllimited="true"/>
  </actuator>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    phases = []
    for target in (0.35, -0.35, 0.0):
        data.ctrl[0] = target
        for _ in range(2000):
            mujoco.mj_step(model, data)
            assert math.isfinite(float(data.qpos[0]))
            assert abs(float(data.qpos[0])) < math.pi / 4 + 0.02
        angle = float(data.qpos[0])
        velocity = float(data.qvel[0])
        assert abs(angle - target) < 0.03, (target, angle)
        assert abs(velocity) < 0.03, (target, velocity)
        phases.append({"target": target, "final_angle": angle, "final_velocity": velocity})
    result = {"verified": True, "engine": mujoco.__version__, "steps_per_phase": 2000,
              "phases": phases, "position_tolerance": 0.03, "velocity_tolerance": 0.03}
    Path("mujoco_reversal_result.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    run()
