"""Conservative continuous clearance for finite-width links and multiple disks."""
import json,math
from pathlib import Path

L1,L2=0.7,0.5
LINK_RADIUS=0.025
MARGIN=0.02
OBSTACLES=[((0.35,0.0),0.08),((-0.4,0.0),0.08)]

def segment_distance(a,b,c):
    vx,vy=b[0]-a[0],b[1]-a[1]
    denom=vx*vx+vy*vy
    t=max(0.,min(1.,((c[0]-a[0])*vx+(c[1]-a[1])*vy)/denom)) if denom else 0.
    return math.hypot(a[0]+t*vx-c[0],a[1]+t*vy-c[1])

def clearance(q):
    a,b=q
    elbow=(L1*math.cos(a),L1*math.sin(a))
    tip=(elbow[0]+L2*math.cos(a+b),elbow[1]+L2*math.sin(a+b))
    return min(min(segment_distance((0.,0.),elbow,c),segment_distance(elbow,tip,c))-r-LINK_RADIUS for c,r in OBSTACLES)

def certify(start,end,steps=256):
    da,db=end[0]-start[0],end[1]-start[1]
    speed_bound=L1*abs(da)+L2*(abs(da)+abs(db))
    samples=[clearance((start[0]+da*i/steps,start[1]+db*i/steps)) for i in range(steps+1)]
    lower=min(samples)-speed_bound/(2*steps)
    return {"safe":lower>=MARGIN,"certified_lower_bound_m":lower,"sampled_minimum_m":min(samples),"steps":steps}

def run():
    safe=certify((math.pi/2,0),(math.pi/2+0.1,-0.1))
    assert safe["safe"],safe
    # Two opposite obstacles: both endpoints clear, sweep crosses first disk.
    crossing=certify((-math.pi/2,0),(math.pi/2,0))
    assert clearance((-math.pi/2,0))>=MARGIN
    assert clearance((math.pi/2,0))>=MARGIN
    assert not crossing["safe"],crossing
    static=certify((0,0),(0,0))
    assert not static["safe"]
    # Check second obstacle also independently rejects a left-pointing arm.
    left=certify((math.pi,0),(math.pi,0))
    assert not left["safe"]
    result={"verified":True,"scope":"2D finite-width capsule links, two static disk obstacles, linear joint interpolation",
            "link_lengths_m":[L1,L2],"link_radius_m":LINK_RADIUS,
            "obstacles":[{"center_m":list(c),"radius_m":r} for c,r in OBSTACLES],
            "required_margin_m":MARGIN,"safe_motion":safe,"endpoint_safe_sweep_unsafe":crossing,
            "first_obstacle_collision":static,"second_obstacle_collision":left,
            "method":"conservative Lipschitz lower bound over continuous interpolation"}
    Path("mujoco_multi_obstacle_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":run()
