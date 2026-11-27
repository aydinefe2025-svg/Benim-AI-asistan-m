"""Conservative circular-obstacle path planning with exact segment clearance checks."""
import json
import math
from pathlib import Path

OBSTACLE = (0.5, 0.0)
RADIUS = 0.15
MARGIN = 0.05
CLEARANCE = RADIUS + MARGIN
START = (0.0, 0.0)
GOAL = (1.0, 0.0)

def segment_distance(a, b, center=OBSTACLE):
    vx, vy = b[0]-a[0], b[1]-a[1]
    wx, wy = center[0]-a[0], center[1]-a[1]
    d = vx*vx + vy*vy
    t = max(0.0, min(1.0, (wx*vx+wy*vy)/d)) if d else 0.0
    return math.hypot(a[0]+t*vx-center[0], a[1]+t*vy-center[1])

def safe_path(points):
    return all(segment_distance(a,b) >= CLEARANCE-1e-12
               for a,b in zip(points,points[1:]))

def plan(start, goal):
    if safe_path([start,goal]):
        return [start,goal]
    # Construct a conservative rectangular bypass, with clearance checked
    # analytically on each segment (not just at sampled waypoints).
    for side in (1,-1):
        y = OBSTACLE[1] + side*(CLEARANCE + 0.1)
        points = [start,(start[0],y),(goal[0],y),goal]
        if safe_path(points):
            return points
    raise ValueError("No safe bypass found")

def run():
    assert not safe_path([START,GOAL]), "Direct path must be blocked"
    path = plan(START,GOAL)
    assert path[0] == START and path[-1] == GOAL
    assert len(path) > 2 and safe_path(path)
    segment_clearances = [segment_distance(a,b)-RADIUS
                          for a,b in zip(path,path[1:])]
    assert min(segment_clearances) >= MARGIN-1e-12
    unblocked_start, unblocked_goal = (0.0,0.5),(1.0,0.5)
    direct = plan(unblocked_start,unblocked_goal)
    assert direct == [unblocked_start,unblocked_goal]
    result = {
        "verified":True,
        "scope":"2D point-path geometry, not robot-link or dynamic obstacle avoidance",
        "obstacle_center_m":list(OBSTACLE),
        "obstacle_radius_m":RADIUS,
        "required_margin_m":MARGIN,
        "blocked_direct_path_rejected":True,
        "safe_waypoints_m":[list(p) for p in path],
        "segment_surface_clearances_m":segment_clearances,
        "minimum_surface_clearance_m":min(segment_clearances),
        "unblocked_direct_path_preserved":True,
        "method":"analytic closest-point distance for each entire line segment"
    }
    Path("mujoco_path_planning_result.json").write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps(result,sort_keys=True))

if __name__ == "__main__":
    run()
