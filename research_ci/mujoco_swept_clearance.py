"""Conservative swept-motion collision certificate for a planar two-link arm.

Checks continuous joint interpolation with a Lipschitz displacement bound;
sampling alone is NOT considered a proof.
"""
import json,math
from pathlib import Path
L1,L2=0.7,0.5
CENTER=(0.35,0.0)
RADIUS=0.08
MARGIN=0.02
def segdist(a,b,c=CENTER):
    dx,dy=b[0]-a[0],b[1]-a[1]
    d=dx*dx+dy*dy
    t=max(0.,min(1.,((c[0]-a[0])*dx+(c[1]-a[1])*dy)/d)) if d else 0.
    return math.hypot(a[0]+t*dx-c[0],a[1]+t*dy-c[1])
def clearance(q):
    a,b=q
    elbow=(L1*math.cos(a),L1*math.sin(a))
    tip=(elbow[0]+L2*math.cos(a+b),elbow[1]+L2*math.sin(a+b))
    return min(segdist((0,0),elbow),segdist(elbow,tip))-RADIUS
def certify(start,end,steps=128):
    da,db=end[0]-start[0],end[1]-start[1]
    # Every material point of the arm moves no faster than this bound
    # per unit normalized trajectory time.
    speed_bound=L1*abs(da)+L2*(abs(da)+abs(db))
    samples=[clearance((start[0]+da*i/steps,start[1]+db*i/steps)) for i in range(steps+1)]
    # Nearest sample is at most 1/(2*steps) in normalized time.
    certified_lower=min(samples)-speed_bound/(2*steps)
    return {"sampled_minimum_m":min(samples),"certified_lower_bound_m":certified_lower,
            "safe":certified_lower>=MARGIN,"samples":steps}
def run():
    # Safe: arm points upward and rotates only slightly.
    safe=certify((math.pi/2,0),(math.pi/2+0.1,-0.1))
    assert safe["safe"],safe
    # Unsafe: arm swings through an obstacle even though both endpoints
    # are clear; a test of endpoints alone would miss this.
    crossing=certify((-math.pi/2,0),(math.pi/2,0))
    assert clearance((-math.pi/2,0))>MARGIN
    assert clearance((math.pi/2,0))>MARGIN
    assert not crossing["safe"],crossing
    # Reject static colliding pose.
    colliding=certify((0,0),(0,0))
    assert not colliding["safe"]
    result={"verified":True,"scope":"2D zero-thickness links, fixed circular obstacle; conservative continuous joint interpolation bound",
            "required_margin_m":MARGIN,"safe_motion":safe,"endpoint_safe_but_swept_unsafe":crossing,
            "static_collision":colliding,"proof_method":"Lipschitz maximum point displacement between neighboring joint-space samples"}
    Path("mujoco_swept_clearance_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))
if __name__=="__main__":run()
