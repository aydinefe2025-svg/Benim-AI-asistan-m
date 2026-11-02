"""Independent two-joint robot position-control validation."""
import json
import math
from pathlib import Path
import mujoco

XML = """
<mujoco model="two_joint_arm">
  <option timestep="0.002" gravity="0 0 0"/>
  <worldbody>
    <body name="link1">
      <joint name="shoulder" type="hinge" axis="0 0 1" range="-60 60" limited="true" damping="1"/>
      <geom type="capsule" fromto="0 0 0 0.7 0 0" size="0.04" mass="1"/>
      <body name="link2" pos="0.7 0 0">
        <joint name="elbow" type="hinge" axis="0 0 1" range="-60 60" limited="true" damping="1"/>
        <geom type="capsule" fromto="0 0 0 0.5 0 0" size="0.035" mass="0.5"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <position name="shoulder_motor" joint="shoulder" kp="60" kv="12" ctrlrange="-0.6 0.6" ctrllimited="true"/>
    <position name="elbow_motor" joint="elbow" kp="50" kv="10" ctrlrange="-0.6 0.6" ctrllimited="true"/>
  </actuator>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    phases = []
    for targets in ((0.3, -0.25), (-0.25, 0.3), (0.0, 0.0)):
        data.ctrl[:] = targets
        for _ in range(3000):
            mujoco.mj_step(model, data)
            assert all(math.isfinite(float(q)) for q in data.qpos)
            assert all(abs(float(q)) < math.pi / 3 + 0.02 for q in data.qpos)
        final = [float(x) for x in data.qpos]
        speeds = [float(x) for x in data.qvel]
        assert max(abs(a-b) for a,b in zip(final,targets)) < 0.04, (targets, final)
        assert max(abs(x) for x in speeds) < 0.04, speeds
        phases.append({"target":list(targets),"final":final,"velocity":speeds})
    result = {"verified":True,"engine":mujoco.__version__,"joint_count":2,"steps_per_phase":3000,"phases":phases,"position_tolerance":0.04,"velocity_tolerance":0.04}
    Path("mujoco_two_joint_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__ == "__main__":
    run()
