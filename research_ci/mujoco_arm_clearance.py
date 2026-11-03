"""Validate entire two-link arm clearance, including elbow and links."""
import json
import math
from pathlib import Path

L1,L2=0.7,0.5
OBSTACLE=(0.35,0.0)
RADIUS=0.08
MARGIN=0.02

def arm(q1,q2):
    elbow=(L1*math.cos(q1),L1*math.sin(q1))
    tip=(elbow[0]+L2*math.cos(q1+q2),elbow[1]+L2*math.sin(q1+q2))
    return (0.0,0.0),elbow,tip

def segment_distance(a,b,c):
    vx,vy=b[0]-a[0],b[1]-a[1]
    denom=vx*vx+vy*vy
    t=max(0.0,min(1.0,((c[0]-a[0])*vx+(c[1]-a[1])*vy)/denom)) if denom else 0
    return math.hypot(a[0]+t*vx-c[0],a[1]+t*vy-c[1])

def clearance(q1,q2):
    base,elbow,tip=arm(q1,q2)
    return min(segment_distance(base,elbow,OBSTACLE),
               segment_distance(elbow,tip,OBSTACLE))-RADIUS

def run():
    cases=[
      ("first_link_collision",0.0,0.0,False),
      ("second_link_collision",math.pi/2,-math.pi/2,True),
      ("clear_upward",math.pi/2,0.0,True),
      ("first_link_near_miss",0.35,0.0,True)
    ]
    # The obstacle at (0.35,0) is inside the first link when q1=0.
    # For q1=pi/2, the second link at y=0.7 is also clear.
    results=[]
    for name,q1,q2,expected_safe in cases:
        c=clearance(q1,q2)
        safe=c>=MARGIN-1e-12
        assert safe==expected_safe,(name,c,safe)
        results.append({"case":name,"q1_rad":q1,"q2_rad":q2,
                        "surface_clearance_m":c,"safe":safe})
    # A tip-only check misses a first-link collision.
    _,_,tip=arm(0.0,0.0)
    tip_clearance=math.dist(tip,OBSTACLE)-RADIUS
    assert tip_clearance>MARGIN and clearance(0.0,0.0)<0
    result={"verified":True,"scope":"static 2D zero-thickness two-link arm, no swept-volume guarantee",
            "link_lengths_m":[L1,L2],"obstacle_center_m":list(OBSTACLE),
            "obstacle_radius_m":RADIUS,"required_margin_m":MARGIN,
            "tip_only_check_misses_collision":True,"cases":results}
    Path("mujoco_arm_clearance_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    run()
