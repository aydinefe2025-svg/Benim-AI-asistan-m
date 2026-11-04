"""Fail-closed safety gate for finite-width arm commands."""
import json
from pathlib import Path
from mujoco_multi_obstacle import certify

def gate(current,requested):
    certificate=certify(current,requested)
    if certificate["safe"]:
        return {"accepted":True,"command":list(requested),"certificate":certificate}
    return {"accepted":False,"command":list(current),"certificate":certificate}

def run():
    safe_start=(1.5707963267948966,0.0)
    allowed=gate(safe_start,(safe_start[0]+0.1,-0.1))
    assert allowed["accepted"]
    assert allowed["command"]==[safe_start[0]+0.1,-0.1]
    blocked=gate((-1.5707963267948966,0.0),(1.5707963267948966,0.0))
    assert not blocked["accepted"]
    assert blocked["command"]==[-1.5707963267948966,0.0]
    collision=gate((0.0,0.0),(0.0,0.0))
    assert not collision["accepted"]
    assert collision["command"]==[0.0,0.0]
    result={"verified":True,"safe_command":allowed,"blocked_sweep":blocked,
            "blocked_collision":collision,
            "scope":"2D mathematical command authorization; does not command or stop physical hardware"}
    Path("mujoco_safety_gate_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":run()
