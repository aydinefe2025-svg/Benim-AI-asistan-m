"""Time-parametrized two-joint trajectory: velocity, limits and endpoint checks."""
import json
import math
from pathlib import Path
import mujoco

XML = """
<mujoco model="trajectory">
<option timestep="0.002" gravity="0 0 0"/>
<worldbody><body><joint name="shoulder" type="hinge" axis="0 0 1" range="-90 90" limited="true" damping="1"/>
<geom type="capsule" fromto="0 0 0 0.7 0 0" size="0.04" mass="1"/>
<body pos="0.7 0 0"><joint name="elbow" type="hinge" axis="0 0 1" range="-90 90" limited="true" damping="1"/>
<geom type="capsule" fromto="0 0 0 0.5 0 0" size="0.035" mass="0.5"/>
<site name="tip" pos="0.5 0 0" size="0.01"/></body></body></worldbody>
<actuator><position joint="shoulder" kp="60" kv="12" ctrlrange="-1.4 1.4" ctrllimited="true"/>
<position joint="elbow" kp="50" kv="10" ctrlrange="-1.4 1.4" ctrllimited="true"/></actuator>
</mujoco>
"""

def smoothstep(u):
    return u*u*(3-2*u)

def run():
    model=mujoco.MjModel.from_xml_string(XML)
    data=mujoco.MjData(model)
    waypoints=[(0.0,0.0),(0.3,-0.25),(-0.2,0.3),(0.0,0.0)]
    steps_per_segment=1500
    dt=float(model.opt.timestep)
    max_speed=0.0
    max_tracking_error=0.0
    segments=[]
    for start, end in zip(waypoints,waypoints[1:]):
        for k in range(steps_per_segment):
            u=smoothstep((k+1)/steps_per_segment)
            desired=[a+(b-a)*u for a,b in zip(start,end)]
            data.ctrl[:]=desired
            mujoco.mj_step(model,data)
            q=[float(v) for v in data.qpos]
            speed=max(abs(float(v)) for v in data.qvel)
            error=max(abs(a-b) for a,b in zip(q,desired))
            assert all(math.isfinite(v) for v in q)
            assert max(abs(v) for v in q)<math.pi/2+0.02
            assert speed<1.5, ("Joint speed limit exceeded",speed)
            max_speed=max(max_speed,speed)
            max_tracking_error=max(max_tracking_error,error)
        endpoint_error=max(abs(float(q)-v) for q,v in zip(data.qpos,end))
        assert endpoint_error<0.04, (end,endpoint_error)
        segments.append({"target":list(end),"endpoint_error_rad":endpoint_error})
    result={"verified":True,"engine":mujoco.__version__,"segments":segments,"steps_per_segment":steps_per_segment,"dt_seconds":dt,"max_joint_speed_rad_s":max_speed,"max_tracking_error_rad":max_tracking_error,"joint_speed_limit_rad_s":1.5,"endpoint_tolerance_rad":0.04,"note":"Joint-space smoothstep motion; obstacle avoidance not yet tested."}
    Path("mujoco_trajectory_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    run()
