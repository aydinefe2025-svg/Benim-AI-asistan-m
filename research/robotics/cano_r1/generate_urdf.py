"""Generate an illustrative, kinematically consistent URDF from CANO-R1 CAD.

No real actuators, certified materials, sensors, electronics or controls. The
inertial density is a hypothetical *plastic-only* estimate; not motor inertia.
"""
from pathlib import Path
from xml.etree.ElementTree import Element,SubElement,ElementTree,indent
import json
import numpy as np
from assembly_model import Assembly,NAMES,JOINT_LIMITS,BASE_HEIGHT_MM,LINKS_MM

ROOT=Path(__file__).parent
ASSUMED_PRINT_DENSITY_KG_M3=1250.
MESH_SCALE=0.001
OFFSETS_M={'base':(0,0,0),'yaw':(0,0,0),'upper':(0,.007,0),'forearm':(0,-.007,0),'wrist':(0,.007,0),'gripper':(0,0,0)}


def write_urdf(path=ROOT/'CANO_R1_CAD_BETA.urdf'):
    arm=Assembly()
    robot=Element('robot',{'name':'cano_r1_cad_beta'})
    masses={}
    rgb={'base':'0.21 0.24 0.28 1','yaw':'0.45 0.47 0.50 1','upper':'0.95 0.56 0.18 1','forearm':'0.20 0.56 0.82 1','wrist':'0.31 0.65 0.55 1','gripper':'0.81 0.29 0.28 1'}
    for n,m in zip(NAMES,arm.meshes):
        link=SubElement(robot,'link',{'name':n})
        volume_mm3=float(m.volume)
        mass_kg=volume_mm3 * 1e-9 * ASSUMED_PRINT_DENSITY_KG_M3
        masses[n]={'volume_mm3':round(volume_mm3,4),'assumed_plastic_only_mass_kg':round(mass_kg,7)}
        for tag in ['visual','collision']:
            element=SubElement(link,tag)
            SubElement(element,'origin',{'xyz':' '.join(str(x) for x in OFFSETS_M[n]),'rpy':'0 0 0'})
            g=SubElement(element,'geometry')
            SubElement(g,'mesh',{'filename':f'meshes/{n}.stl','scale':'0.001 0.001 0.001'})
            if tag=='visual':
                mat=SubElement(element,'material',{'name':n+'_paint'})
                SubElement(mat,'color',{'rgba':rgb[n]})
        iner=SubElement(link,'inertial')
        cm=np.asarray(m.center_mass,float)*1e-3+np.array(OFFSETS_M[n],float)
        SubElement(iner,'origin',{'xyz':' '.join(f'{v:.9g}' for v in cm),'rpy':'0 0 0'})
        SubElement(iner,'mass',{'value':f'{mass_kg:.10g}'})
        I=np.asarray(m.moment_inertia,float)*(mass_kg/volume_mm3)*1e-6
        SubElement(iner,'inertia',{k:f'{I[i,j]:.12g}' for k,i,j in [('ixx',0,0),('ixy',0,1),('ixz',0,2),('iyy',1,1),('iyz',1,2),('izz',2,2)]})
    def joint(name,parent,child,xyz,axis,kind='revolute',limit=None):
        j=SubElement(robot,'joint',{'name':name,'type':kind})
        SubElement(j,'parent',{'link':parent})
        SubElement(j,'child',{'link':child})
        SubElement(j,'origin',{'xyz':' '.join(f'{x:.9g}' for x in xyz),'rpy':'0 0 0'})
        if kind=='revolute':
            SubElement(j,'axis',{'xyz':' '.join(str(x) for x in axis)})
            lo,hi=limit
            # Velocity/effort are placeholder caps for renderer compatibility,
            # NOT real motor ratings; release gate explicitly blocks hardware.
            SubElement(j,'limit',{'lower':f'{np.deg2rad(lo):.10g}','upper':f'{np.deg2rad(hi):.10g}',
                                   'effort':'1.0','velocity':'1.0'})
    # Fixed base world link represented by the base itself: root is `base`.
    joint('base_yaw','base','yaw',(0,0,BASE_HEIGHT_MM/1000),(0,0,1),limit=JOINT_LIMITS[0])
    joint('shoulder_pitch','yaw','upper',(0,0,0),(0,-1,0),limit=JOINT_LIMITS[1])
    joint('elbow_pitch','upper','forearm',(LINKS_MM[0]/1000,0,0),(0,-1,0),limit=JOINT_LIMITS[2])
    joint('wrist_pitch','forearm','wrist',(LINKS_MM[1]/1000,0,0),(0,-1,0),limit=JOINT_LIMITS[3])
    joint('gripper_fixed','wrist','gripper',(LINKS_MM[2]/1000,0,0),(0,0,1),kind='fixed')
    indent(robot)
    ElementTree(robot).write(path,encoding='utf-8',xml_declaration=True)
    (ROOT/'results'/'estimated_plastic_masses.json').write_text(json.dumps({'density_assumed_kg_m3':ASSUMED_PRINT_DENSITY_KG_M3,
        'NOT_measured_or_motor_mass':True,'parts':masses},indent=2),encoding='utf-8')
    return str(path)

if __name__=='__main__':print(write_urdf())