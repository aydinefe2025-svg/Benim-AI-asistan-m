import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from assembly_model import (Assembly,NAMES,JOINT_LIMITS,BASE_HEIGHT_MM,LINKS_MM,
                            START,WAY,END,ORIG_START,forward_mm,assess_pose,tip_distance_mm,
                            PAIRS,separated_axis_lower_bound,Body,convex_hull_intersection)
from continuous_gate import certify,bounds_for_deltas
from generate_urdf import write_urdf,ROOT
from release_gate import release_status


class IntegratedCAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=Assembly()

    def test_real_original_stl_mesh_topology_six_parts(self):
        for n,m in zip(NAMES,self.a.meshes):
            with self.subTest(n=n):
                self.assertTrue(m.is_watertight)
                self.assertTrue(m.is_winding_consistent)
                self.assertGreater(m.volume,0)
                self.assertGreater(len(m.faces),100)

    def test_nonconvex_booleans_and_through_hole(self):
        upper=self.a.meshes[2]
        self.assertGreater(upper.convex_hull.volume,upper.volume*1.01)
        verts=np.asarray(upper.vertices,float)
        near_bore=np.sqrt(verts[:,0]**2+verts[:,2]**2)
        r_min=float(near_bore[(near_bore>0.1)&(near_bore<2.5)].min())
        # A Ø3 mm illustrative pin passes through the Ø4.2 mm polygonal bore.
        # 48 facets: inradius of bore ~2.0955 mm (nominal rad2.1 mm).
        self.assertGreater(r_min,2.09)
        self.assertLess(r_min,2.11)
        self.assertGreater(r_min-1.5,0.58)
        self.assertLess(r_min-1.5,0.61)

    def test_convex_hull_fills_bore_false_positive_risk(self):
        # The original CSG link contains a through-bore. Its convex hull fills
        # the void; that overlap alone is NOT exact solid contact evidence.
        pin=trimesh.creation.cylinder(radius=1.5,height=8,sections=48)
        pin.apply_transform(trimesh.geometry.align_vectors([0,0,1],[0,1,0]))
        from scipy.spatial import ConvexHull
        def body(n,v):
            norms=ConvexHull(v).equations[:,:3]
            return Body(n,v,np.zeros((0,3),int),v.mean(axis=0),norms,float(np.linalg.norm(v,axis=1).max()))
        upper=self.a.meshes[2]
        self.assertTrue(convex_hull_intersection(body('hole',np.asarray(upper.vertices)),body('pin',np.asarray(pin.vertices))))

    def test_local_frames_and_mount_offsets(self):
        q=START;b=self.a.bodies(q);p=forward_mm(q)
        self.assertEqual(len(b),6)
        self.assertAlmostEqual(float(b[0].vertices[:,2].min()),0,places=6)
        self.assertAlmostEqual(float(b[1].center[2]),70+np.asarray(self.a.meshes[1].vertices)[:,2].mean(),places=5)
        self.assertEqual(len(p),4)

    def test_urdf_tree_and_mesh_units(self):
        write_urdf()
        root=ET.parse(ROOT/'CANO_R1_CAD_BETA.urdf').getroot()
        self.assertEqual(len(root.findall('link')),6)
        self.assertEqual(len(root.findall('joint')),5)
        for mesh in root.findall('.//mesh'):
            self.assertEqual(mesh.get('scale'),'0.001 0.001 0.001')
            self.assertTrue((ROOT/mesh.get('filename')).is_file())
        for inertia in root.findall('.//inertia'):
            tensor=np.array([[float(inertia.get('ixx')),float(inertia.get('ixy')),float(inertia.get('ixz'))],
                             [float(inertia.get('ixy')),float(inertia.get('iyy')),float(inertia.get('iyz'))],
                             [float(inertia.get('ixz')),float(inertia.get('iyz')),float(inertia.get('izz'))]])
            self.assertGreater(float(np.linalg.eigvalsh(tensor).min()),0)

    def test_independent_urdf_forward_kinematics(self):
        root=ET.parse(ROOT/'CANO_R1_CAD_BETA.urdf').getroot()
        joint_map={j.find('child').get('link'):j for j in root.findall('joint')}
        for q in (START,WAY,END,ORIG_START):
            p=np.zeros(3);rot=np.eye(3)
            got=[]
            for name,a in zip(('yaw','upper','forearm','wrist'),q):
                j=joint_map[name]
                xyz=np.array([float(v) for v in j.find('origin').get('xyz').split()])*1000
                axis=np.array([float(v) for v in j.find('axis').get('xyz').split()])
                p=p+rot@xyz
                rot=rot@Rotation.from_rotvec(math.radians(a)*axis).as_matrix()
                got.append(p.copy())
            tip=p+rot@np.array([LINKS_MM[2],0,0])
            actual=forward_mm(q)
            self.assertLess(float(np.linalg.norm(got[0]-actual[0])),1e-6)
            self.assertLess(float(np.linalg.norm(got[2]-actual[1])),1e-6)
            self.assertLess(float(np.linalg.norm(got[3]-actual[2])),1e-6)
            self.assertLess(float(np.linalg.norm(tip-actual[3])),1e-6)

    def test_new_start_and_two_waypoint_endpoints(self):
        for q in (START,WAY,END):
            status=assess_pose(self.a,q,margin_mm=2)
            self.assertTrue(status['pose_safe_proved'],msg=status)
            self.assertGreater(status['min_reported_gap_mm'],2)

    def test_prior_start_fails_new_cad(self):
        bad=assess_pose(self.a,ORIG_START,margin_mm=2)
        self.assertFalse(bad['pose_safe_proved'])
        self.assertTrue(any('inconclusive' in x['status'] or 'insufficient' in x['status'] for x in bad['checks']))

    def test_full_swept_path_leg1_plus_joint_offset_box(self):
        ans=certify(self.a,START,WAY,threshold_mm=2,offset_deg=1,max_depth=11,max_poses=1500)
        self.assertEqual(ans.verdict,'certified_safe')
        self.assertGreater(ans.clearance_lower_bound_mm,2)
        self.assertEqual(ans.intervals_inconclusive,0)

    def test_full_swept_path_leg2_plus_joint_offset_box(self):
        ans=certify(self.a,WAY,END,threshold_mm=2,offset_deg=1,max_depth=11,max_poses=1500)
        self.assertEqual(ans.verdict,'certified_safe')
        self.assertGreater(ans.clearance_lower_bound_mm,2)
        self.assertEqual(ans.intervals_inconclusive,0)

    def test_certifier_fails_closed_on_budget_limit(self):
        ans=certify(self.a,START,WAY,threshold_mm=2,offset_deg=1,max_depth=2,max_poses=20)
        self.assertEqual(ans.verdict,'inconclusive')
        self.assertIsNone(ans.clearance_lower_bound_mm)

    def test_zero_uncertainty_cannot_worsen_certified_envelope(self):
        z=certify(self.a,START,WAY,threshold_mm=2,offset_deg=0,max_depth=11,max_poses=1500)
        u=certify(self.a,START,WAY,threshold_mm=2,offset_deg=1,max_depth=11,max_poses=1500)
        self.assertEqual(z.verdict,u.verdict)
        self.assertGreater(z.clearance_lower_bound_mm,u.clearance_lower_bound_mm)

    def test_all_frames_reject_out_of_range_joint(self):
        with self.assertRaises(ValueError): forward_mm((121,45,-80,35))
        with self.assertRaises(ValueError): forward_mm((0,45,-80,float('nan')))
        with self.assertRaises(ValueError): certify(self.a,START,WAY,offset_deg=7)

    def test_winding_flip_negative_control(self):
        m=self.a.meshes[2].copy();m.invert()
        self.assertLess(float(m.volume),0)

    def test_revised_start_end_effector_task_shift_blocks_physical(self):
        mm=tip_distance_mm(ORIG_START,START)
        self.assertAlmostEqual(mm,25.0,places=5)
        g=release_status(max_task_shift_mm=5)
        self.assertFalse(g['physical_release_allowed'])
        self.assertFalse(g['task_position_gate_passed'])
        self.assertGreater(len(g['missing_independent_hardware_evidence']),8)

    def test_no_motor_control_code_or_live_release(self):
        self.assertFalse(release_status({})['physical_release_allowed'])
        self.assertFalse(release_status({k:True for k in []})['physical_release_allowed'])

if __name__=='__main__':unittest.main()