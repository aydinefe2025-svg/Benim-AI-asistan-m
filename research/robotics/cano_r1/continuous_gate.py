"""Fail-closed interval clearance checker for 6-part original CAD beta assembly.

Bounded by rotation chord length <= magnitude of angular difference (radians).
A positive projected gap along any separating normal is a sufficient certificate
for convex hull non-intersection, even if the actual solids are nonconvex.
Joint offsets are a 4-dimensional deterministic uncertainty BOX, not samples.
"""
from dataclasses import dataclass,asdict
import math
from assembly_model import Assembly,PAIRS,NAMES,LINKS_MM,JOINT_LIMITS,forward_mm,separated_axis_lower_bound

@dataclass
class Result:
    verdict: str
    pose_evaluations: int
    intervals_certified: int
    intervals_inconclusive: int
    clearance_lower_bound_mm: float | None
    diagnostic_min_sampled_gap_mm: float | None
    reason: str


def bounds_for_deltas(assembly, dq_deg):
    """Max 3D rigid-body vertex move under absolute 4-joint angle variations.

    The original link anchors each have contributions from upstream link rotations,
    local vertex rotational uncertainty includes yaw and cumulative pitch.
    No assumption that offsets are independent uniform RVs is needed.
    """
    dy,ds,de,dw=[math.radians(abs(float(v))) for v in dq_deg]
    link_frame_angles=[dy+ds,dy+ds+de,dy+ds+de+dw]
    p1=LINKS_MM[0]*link_frame_angles[0]
    p2=p1+LINKS_MM[1]*link_frame_angles[1]
    p3=p2+LINKS_MM[2]*link_frame_angles[2]
    radii=assembly.local_radius
    # pedestal fixed; yaw rotor rotates about world Z at fixed anchor
    return [0.,radii[1]*dy,
            radii[2]*link_frame_angles[0],
            p1+radii[3]*link_frame_angles[1],
            p2+radii[4]*link_frame_angles[2],
            p3+radii[5]*link_frame_angles[2]]


def interpolate(qa,qb,t):
    return tuple(x+(y-x)*t for x,y in zip(qa,qb))


def certify(assembly,qa,qb,threshold_mm=2.,offset_deg=1.,max_depth=14,max_poses=5000):
    if not (0 < threshold_mm < 50):raise ValueError('threshold must be 0..50mm')
    if not (0 <= offset_deg <= 3):raise ValueError('offset must be 0..3 degrees')
    for j,(lo,hi) in enumerate(JOINT_LIMITS):
        if min(qa[j],qb[j])-offset_deg < lo or max(qa[j],qb[j])+offset_deg > hi:
            raise ValueError('Joint uncertainty exceeds angle limit')
    abs_offsets=bounds_for_deltas(assembly,[offset_deg]*4)
    cache={}; certified=0; unknown=0; global_lower=float('inf'); sample_min=float('inf')
    def scan(t):
        nonlocal sample_min
        if t not in cache:
            if len(cache)>=max_poses:return None
            bodies=assembly.bodies(interpolate(qa,qb,t))
            gaps=[separated_axis_lower_bound(bodies[i],bodies[j]) for i,j in PAIRS]
            ground=[float(b.vertices[:,2].min()) for b in bodies[2:]]
            vals=gaps+ground
            sample_min=min(sample_min,*vals)
            cache[t]=(gaps,ground)
        return cache[t]
    for t in (0.,1.):
        scan(t)
    def walk(a,b,depth):
        nonlocal certified,unknown,global_lower
        t=(a+b)/2
        scanned=scan(t)
        if scanned is None:
            unknown+=1;return False
        gaps,ground=scanned
        dq=[abs(y-x)*(b-a)/2 for x,y in zip(qa,qb)]
        move=bounds_for_deltas(assembly,dq)
        candidates=[g - move[i]-move[j] -abs_offsets[i]-abs_offsets[j] for (i,j),g in zip(PAIRS,gaps)]
        candidates += [g-move[i]-abs_offsets[i] for i,g in enumerate(ground,start=2)]
        bound=min(candidates)-0.001 # 1-micron numeric guard in mm
        if bound>threshold_mm:
            certified+=1;global_lower=min(global_lower,bound);return True
        if depth>=max_depth:
            unknown+=1;return False
        left=walk(a,t,depth+1);right=walk(t,b,depth+1)
        return left and right
    result=walk(0.,1.,0)
    return Result('certified_safe' if result else 'inconclusive',len(cache),certified,unknown,
                  round(global_lower,5) if result else None,
                  round(sample_min,5) if sample_min<float('inf') else None,
                  'Hull separation and conservative swept/offset bounds; no physical certification.' if result else 'Could not prove all clearances; never assume inconclusive is safe.')


if __name__=='__main__':
    from assembly_model import START,WAY,END,ORIG_START
    a=Assembly()
    for n,x,y in [('start-way',START,WAY),('way-end',WAY,END),('oldstart-way',ORIG_START,WAY)]:
        print(n,asdict(certify(a,x,y)))