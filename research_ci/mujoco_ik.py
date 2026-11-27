"""Two-link planar inverse kinematics checked against MuJoCo forward kinematics."""
import json
import math
from pathlib import Path
import mujoco

L1, L2 = 0.7, 0.5
XML = """
<mujoco model="planar_ik">
  <option timestep="0.002" gravity="0 0 0"/>
  <worldbody>
    <body name="link1">
      <joint name="shoulder" type="hinge" axis="0 0 1" range="-90 90" limited="true" damping="1"/>
      <geom type="capsule" fromto="0 0 0 0.7 0 0" size="0.04" mass="1"/>
      <body name="link2" pos="0.7 0 0">
        <joint name="elbow" type="hinge" axis="0 0 1" range="-90 90" limited="true" damping="1"/>
        <geom type="capsule" fromto="0 0 0 0.5 0 0" size="0.035" mass="0.5"/>
        <site name="tip" pos="0.5 0 0" size="0.01"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <position joint="shoulder" kp="60" kv="12" ctrlrange="-1.4 1.4" ctrllimited="true"/>
    <position joint="elbow" kp="50" kv="10" ctrlrange="-1.4 1.4" ctrllimited="true"/>
  </actuator>
</mujoco>
"""

def solve_ik(x, y):
    c = (x*x + y*y - L1*L1 - L2*L2) / (2*L1*L2)
    if abs(c) > 1:
        raise ValueError("Unreachable target")
    q2 = math.acos(max(-1.0, min(1.0, c)))
    q1 = math.atan2(y, x) - math.atan2(L2*math.sin(q2), L1 + L2*math.cos(q2))
    return q1, q2

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    targets = [(1.0, 0.35), (0.9, 0.55), (1.1, 0.25)]
    records = []
    for x, y in targets:
        angles = solve_ik(x, y)
        assert all(abs(q) <= math.pi/2 for q in angles), angles
        data.ctrl[:] = angles
        for _ in range(4000):
            mujoco.mj_step(model, data)
        observed = [float(data.site_xpos[site_id, 0]), float(data.site_xpos[site_id, 1])]
        error = math.hypot(observed[0]-x, observed[1]-y)
        velocity = max(abs(float(v)) for v in data.qvel)
        assert error < 0.02, (x, y, observed, error)
        assert velocity < 0.03, velocity
        records.append({"target_xy":[x,y],"joint_target_radians":list(angles),"observed_xy":observed,"error_m":error,"max_joint_speed":velocity})
    try:
        solve_ik(2.0, 0.0)
    except ValueError:
        unreachable_rejected = True
    else:
        raise AssertionError("Unreachable target was accepted")
    result = {"verified":True,"engine":mujoco.__version__,"model":"two-link planar arm","targets":records,"unreachable_target_rejected":unreachable_rejected,"position_tolerance_m":0.02}
    Path("mujoco_ik_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__ == "__main__":
    run()
