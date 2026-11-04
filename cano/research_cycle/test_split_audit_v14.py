import unittest
from split_audit import audit

class AllSplitsAuditTests(unittest.TestCase):
    def test_three_way_scene_leakage_is_complete(self):
        rows=[]
        for i, split in enumerate(('train','val','test')):
            rows.append({'pair_id':str(i),'scene_id':'same-scene','split':split,'image_a_sha256':format(i+1,'064x'),'image_b_sha256':format(i+10,'064x')})
        r=audit(rows)
        self.assertFalse(r['ok'])
        scenes=[x for x in r['issues'] if x['kind']=='scene_leakage']
        self.assertEqual(len(scenes),1)
        self.assertEqual(scenes[0]['splits'],['test','train','val'])

    def test_three_way_image_leakage_is_complete(self):
        rows=[]
        for i, split in enumerate(('train','val','test')):
            rows.append({'pair_id':str(i),'scene_id':f'scene-{i}','split':split,'image_a_sha256':'a'*64,'image_b_sha256':format(i+10,'064x')})
        r=audit(rows)
        issues=[x for x in r['issues'] if x['kind']=='image_leakage']
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0]['splits'],['test','train','val'])

    def test_no_leakage(self):
        rows=[{'pair_id':str(i),'scene_id':f'scene-{i}','split':split,'image_a_sha256':format(i+1,'064x'),'image_b_sha256':format(i+10,'064x')} for i,split in enumerate(('train','val','test'))]
        self.assertTrue(audit(rows)['ok'])

if __name__=='__main__': unittest.main()