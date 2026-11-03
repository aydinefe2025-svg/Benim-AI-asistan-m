"""Verify obstacle contact detection and clearance in MuJoCo."""
import json
from pathlib import Path
import mujoco

XML = """
<mujoco model="obstacle_detection">
<option timestep="0.002" gravity="0 0 0"/>
<worldbody>
  <body name="probe" pos="0 0 0">\n    <freejoint/>
    <geom name="probe_geom" type="sphere" size="0.1" contype="1" conaffinity="1"/>
  </body>
  <body name="obstacle" pos="0.5 0 0">
    <geom name="obstacle_geom" type="sphere" size="0.1" contype="1" conaffinity="1"/>
  </body>
</worldbody>
</mujoco>
"""

def run():
    model = mujoco.MjModel.from_xml_string(XML)
    data = mujoco.MjData(model)
    probe = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "probe_geom")
    obstacle = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "obstacle_geom")
    cases = [(0.0, False), (0.29, False), (0.35, True), (0.5, True)]
    records = []
    for x, expected_contact in cases:
        data.qpos[:3] = [x, 0, 0]
        mujoco.mj_forward(model, data)
        distances = [float(data.contact[i].dist) for i in range(data.ncon)
                     if {int(data.contact[i].geom1), int(data.contact[i].geom2)} == {probe, obstacle}]
        has_contact = bool(distances)
        assert has_contact == expected_contact, (x, expected_contact, distances)
        records.append({"probe_x_m":x,"expected_contact":expected_contact,
                        "contact_detected":has_contact,"contact_distances_m":distances})
    result = {"verified":True,"engine":mujoco.__version__,"cases":records,
              "scope":"Static collision detection only; not autonomous obstacle avoidance"}
    Path("mujoco_obstacle_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__ == "__main__":
    run()
