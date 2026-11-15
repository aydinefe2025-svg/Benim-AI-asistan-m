"""Emit stable evidence + preview for isolated CANO-R1 CAD beta."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,sys,platform,importlib.metadata
import numpy as np
import trimesh
from assembly_model import Assembly,START,WAY,END,ORIG_START,assess_pose,NAMES,tip_distance_mm,PAIRS
from continuous_gate import certify
from generate_urdf import write_urdf
from release_gate import release_status

ROOT=Path(__file__).parent
V=ROOT/'visuals'
V.mkdir(exist_ok=True)
R=ROOT/'results'
R.mkdir(exist_ok=True)


def hashfile(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*512),b''):h.update(b)
    return h.hexdigest()


def evidence():
    write_urdf()
    a=Assembly()
    statuses={n:assess_pose(a,q) for n,q in [('old_start',ORIG_START),('revised_start',START),('waypoint',WAY),('end',END)]}
    routes={n:asdict(certify(a,x,y,threshold_mm=2,offset_deg=1,max_depth=12,max_poses=4000))
            for n,x,y in [('leg_start_to_waypoint',START,WAY),('leg_waypoint_to_end',WAY,END)]}
    manifest={n:{'sha256':hashfile(ROOT/'meshes'/f'{n}.stl'),'triangles':len(m.faces),'volume_mm3':round(float(m.volume),4)}
              for n,m in zip(NAMES,a.meshes)}
    result={
        'schema':'CANO-R1 CAD BETA evidence v1 / never live hardware',
        'build_date':'2026-11-15',
        'source_model':'original parametric OpenSCAD CSG, millimetre geometry; 6 parts',
        'software':{k:importlib.metadata.version(k) for k in ['numpy','scipy','trimesh']},
        'python':platform.python_version(),
        'model_assumptions':{'base_height_mm':70,'links_mm':[120,100,50],'offset_each_joint_deg':1,'target_clearance_mm':2,
                             'material_density_kg_m3':1250,'gripper_actuated':False,'all_motors_measured':False,
                             'actual_tested_gripper_and_wiring':False},
        'cad_meshes':manifest,'joint_collision_pairs_tested':[f'{NAMES[i]}:{NAMES[j]}' for i,j in PAIRS],
        'poses':statuses,'routes':routes,'release_gate':release_status(),
        'known_issues':['Unmeasured drive train, loading, bearings, cables and PLA strength',
                        'Yaw rotor has an idealized unsupported long stem; structural proof not performed',
                        'Joints have through-bores but no shafts, bearings or fastening provisions verified',
                        'Gripper fingers are fixed. No actuator or grip-force/hold test',
                        'Original task endpoint shifted by 25 mm in XY/Z from previous calibration, plus pedestal height change of 10 mm',
                        'Convex hull separability is sufficient to prove no contact only for checked non-adjacent pairs. Joint/mating pairs exempted.'],
        'sources':[{'kind':'user_owned_baseline','url':'https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/blob/main/organism_lab/robot_factory.py'},
                   {'kind':'tool_docs','url':'https://en.wikibooks.org/wiki/OpenSCAD_User_Manual/STL_Import_and_Export'},
                   {'kind':'open_kinematic_standard','url':'https://wiki.ros.org/urdf/XML/joint'}],
        'no_github_ci_verified_in_this_evidence':True,'no_physical_robot_approval':True,
    }
    (R/'results.json').write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
    for n,q in [('revised_start',START),('waypoint',WAY),('end',END)]:
        data=a.scene(q).export(file_type='glb')
        (V/(n+'.glb')).write_bytes(data)
    # Matplotlib static previews are independently generated from transformed STL coordinates.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig=plt.figure(figsize=(15,5.8))
    for k,(name,q) in enumerate([('Başlangıç',START),('Ara duruş',WAY),('Bitiş',END)]):
        ax=fig.add_subplot(1,3,k+1,projection='3d')
        body=a.bodies(q)
        colors=plt.rcParams['axes.prop_cycle'].by_key()['color']
        pts=np.vstack([b.vertices for b in body]);cn=np.mean([pts.min(axis=0),pts.max(axis=0)],axis=0)
        for i,b in enumerate(body):
            triangles=b.vertices[b.faces]
            mesh=Poly3DCollection(triangles,alpha=.55,edgecolors=(0,0,0,.06),linewidths=.08)
            mesh.set_facecolor(colors[i%len(colors)]);ax.add_collection3d(mesh)
        ax.set_xlim(-220,220);ax.set_ylim(-220,220);ax.set_zlim(0,300)
        ax.set_box_aspect((1,1,.77))
        ax.view_init(elev=20,azim=-62)
        ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)');ax.set_zlabel('Z (mm)')
        ax.set_title(f'{name} — CAD beta',fontsize=11)
    fig.suptitle('CANO-R1 | 6 gerçek parametrik CAD gövdesi • bilgisayar simülasyonu, fiziksel kabul değil',fontsize=13)
    fig.tight_layout();fig.savefig(V/'CANO_R1_CAD_3_POSES.png',dpi=160)
    plt.close(fig)
    print('RESULT JSON SHA256',hashfile(R/'results.json'))
    print('ROUTES',[(k,v['verdict'],v['clearance_lower_bound_mm']) for k,v in routes.items()])
    print('RELEASE_ALLOWED',result['release_gate']['physical_release_allowed'])
    print('MESHES',len(manifest),'POSES',len(statuses))
    return result

if __name__=='__main__':evidence()