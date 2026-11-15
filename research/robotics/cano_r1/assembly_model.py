"""CANO-R1 isolated 4DOF kinematic CAD assembly (mm); no robot/hardware access.

Exports/loads original parametric CAD STL. Conservative convex-hull separation
is a *necessary not sufficient* contact test for nonconvex, bored parts.
The 6 physical-looking parts are prototypes. No gearbox, bearings, wiring or
mounting loads have been designed or validated.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import numpy as np
import trimesh
from scipy.spatial import ConvexHull
from scipy.optimize import linprog

ROOT=Path(__file__).parent
MESH_DIR=ROOT/'meshes'
NAMES=('base','yaw','upper','forearm','wrist','gripper')
LINKS_MM=(120.,100.,50.)
JOINT_LIMITS=((-120.,120.),(-25.,100.),(-145.,0.),(-90.,90.))
ORIG_START=(58.06239456061331,48.25074476435316,-137.79018112269497,-58.476333402858195)
START=(58.051905868475146,65.31662010640713,-132.93228787237138,-56.48030241579134)
WAY=(0.,70.,-60.,0.)
END=(-99.19527204686534,63.18664443910737,-15.758830020412233,76.29394698011586)
ADJACENT={(0,1),(1,2),(2,3),(3,4),(4,5)}
PAIRS=tuple((i,j) for i in range(len(NAMES)) for j in range(i+1,len(NAMES)) if (i,j) not in ADJACENT)
Z_GROUND=0.
BASE_HEIGHT_MM=70.


def validate_angles(q):
    if len(q)!=4 or not all(math.isfinite(float(x)) for x in q):
        raise ValueError('Expected 4 finite angles')
    for a,(lo,hi) in zip(q,JOINT_LIMITS):
        if not lo<=a<=hi:raise ValueError('Joint limits')


def Rz(t):
    c,s=math.cos(t),math.sin(t)
    return np.array(((c,-s,0),(s,c,0),(0,0,1)),float)


def Ry_negative(t):
    """Right handed pitch about -Y: positive pitch moves +X upward."""
    c,s=math.cos(t),math.sin(t)
    return np.array(((c,0,-s),(0,1,0),(s,0,c)),float)


def forward_mm(q):
    validate_angles(q)
    yaw,s,e,w=np.deg2rad(q)
    p=[np.array([0.,0.,BASE_HEIGHT_MM])]
    for L,a in zip(LINKS_MM,(s,s+e,s+e+w)):
        p.append(p[-1]+np.array([math.cos(a)*math.cos(yaw),math.cos(a)*math.sin(yaw),math.sin(a)])*L)
    return np.asarray(p)


@dataclass
class Body:
    name: str
    vertices: np.ndarray
    faces: np.ndarray
    center: np.ndarray
    normals: np.ndarray
    radius_about_anchor: float


class Assembly:
    def __init__(self, root=MESH_DIR):
        self.meshes=[]
        self.local_normals=[]
        self.local_radius=[]
        for n in NAMES:
            m=trimesh.load(Path(root)/(n+'.stl'),force='mesh',process=True)
            if not (m.is_watertight and m.is_winding_consistent and m.volume>0):
                raise ValueError(f'CAD mesh topology failed: {n}')
            self.meshes.append(m)
            n=ConvexHull(m.vertices).equations[:,:3]
            n=np.unique(np.round(n,7),axis=0)
            n=n/np.linalg.norm(n,axis=1)[:,None]
            self.local_normals.append(n)
            off=0. if n is None else (7. if len(self.meshes) in (3,5) else -7. if len(self.meshes)==4 else 0.)
            self.local_radius.append(float(np.linalg.norm(m.vertices+np.array([0.,off,0.]),axis=1).max()))

    def bodies(self,q):
        p=forward_mm(q)
        yaw,s,e,w=np.deg2rad(q)
        yawR=Rz(yaw)
        theta=(s,s+e,s+e+w)
        transforms=((np.eye(3),np.zeros(3)),
                    (yawR,np.array([0.,0.,BASE_HEIGHT_MM])),
                    (yawR@Ry_negative(theta[0]),p[0]),
                    (yawR@Ry_negative(theta[1]),p[1]),
                    (yawR@Ry_negative(theta[2]),p[2]),
                    (yawR@Ry_negative(theta[2]),p[3]))
        y_offsets=(0.,0.,7.,-7.,7.,0.)
        out=[]
        for name,m,(R,t),y_off,normals,radius in zip(NAMES,self.meshes,transforms,y_offsets,self.local_normals,self.local_radius):
            local=np.asarray(m.vertices,float)+np.array([0.,y_off,0.])
            verts=local@R.T+t
            out.append(Body(name,verts,np.asarray(m.faces,int),verts.mean(axis=0),normals@R.T,radius))
        return out

    def scene(self,q):
        s=trimesh.Scene()
        for b in self.bodies(q):
            m=trimesh.Trimesh(vertices=b.vertices,faces=b.faces,process=False)
            s.add_geometry(m,geom_name=b.name)
        return s


def convex_hull_intersection(a,b):
    """True if convex HULLS overlap. For concave solids this is conservative/ambiguous.

    Status==2 proves separated convex hulls; status==0 merely indicates that
    hulls may touch, not that the actual nonconvex CAD solids intersect.
    """
    hull=np.vstack([ConvexHull(a.vertices).equations,ConvexHull(b.vertices).equations])
    res=linprog(np.zeros(3),A_ub=hull[:,:3],b_ub=-hull[:,3],bounds=[(None,None)]*3,method='highs')
    if res.status not in (0,2):raise RuntimeError(f'Convex feasibility inconclusive {res.message}')
    return res.status==0


def separated_axis_lower_bound(a,b):
    """Positive number is mathematically sufficient for convex-hull separation.

    If <=0, does NOT imply collision. Vertex/face normals and center axis only:
    can miss a separating edge-edge direction -> conservative inconclusive.
    """
    norms=np.concatenate([a.normals,b.normals],axis=0)
    mid=b.center-a.center
    if np.linalg.norm(mid)>1e-12: norms=np.vstack([norms,mid/np.linalg.norm(mid)])
    norms=np.unique(np.round(norms,7),axis=0)
    norms=norms/np.linalg.norm(norms,axis=1)[:,None]
    aa=a.vertices@norms.T;bb=b.vertices@norms.T
    return float(np.max(np.maximum(bb.min(axis=0)-aa.max(axis=0),aa.min(axis=0)-bb.max(axis=0))))


def assess_pose(assembly,q,margin_mm=2.):
    bodies=assembly.bodies(q)
    rows=[];all_safe=True;any_collision=False
    for i,j in PAIRS:
        a,b=bodies[i],bodies[j]
        gap=separated_axis_lower_bound(a,b)
        if gap>margin_mm:
            status='certified_separate_proxy'
        elif gap>0:
            status='insufficient_margin'
            all_safe=False
        elif convex_hull_intersection(a,b):
            status='hull_overlap_cad_inconclusive'
            all_safe=False
        else:
            status='edge_separation_unknown_margin'
            all_safe=False
        rows.append({'pair':a.name+':'+b.name,'gap_lower_bound_mm':round(gap,5),'status':status})
    for b in bodies[2:]:
        h=float(b.vertices[:,2].min()-Z_GROUND)
        status='certified_ground_separate' if h>margin_mm else ('ground_intersection' if h<0 else 'insufficient_ground_margin')
        if h<0:any_collision=True
        if h<=margin_mm:all_safe=False
        rows.append({'pair':b.name+':ground','gap_lower_bound_mm':round(h,5),'status':status})
    return {'angles_deg':list(q),'pose_safe_proved':all_safe,'any_ground_collision':any_collision,'checks':rows,'min_reported_gap_mm':min(a['gap_lower_bound_mm'] for a in rows)}


def tip_distance_mm(q0,q1):
    return float(np.linalg.norm(forward_mm(q0)[3]-forward_mm(q1)[3]))