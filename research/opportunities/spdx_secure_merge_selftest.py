#!/usr/bin/env python3
"""Local SPDX CLI acceptance: no external customer data, no production writes."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import jsonschema
import spdx_upstream_acceptance as original
import spdx_secure_merge_cli as cli
from spdx_source_patch import load_patched


class SafeInputAndOutput(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dir=Path(self.tmp.name)
        self.sample=self.dir/'doc.spdx.json'
        self.payload=b'{"SPDXID":"SPDXRef-DOCUMENT","name":"fixture"}'
        self.sample.write_bytes(self.payload)
        self.sha=hashlib.sha256(self.payload).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_verified(self):
        data,digest=cli.read_verified_json(self.sample,self.sha)
        self.assertEqual(data['name'],'fixture')
        self.assertEqual(digest,self.sha)

    def test_wrong_digest_rejected(self):
        with self.assertRaises(cli.RejectedInput):
            cli.read_verified_json(self.sample,'0'*64)

    def test_no_follow_symlink(self):
        symlink=self.dir/'alias.spdx.json'
        try:
            symlink.symlink_to(self.sample)
        except (OSError,NotImplementedError) as e:
            self.skipTest(f'creating symlinks requires Windows developer privilege: {e}')
        with self.assertRaises((OSError,ValueError,cli.RejectedInput)):
            cli.read_verified_json(symlink,self.sha)

    def test_hardlink_rejected(self):
        alias=self.dir/'alias.spdx.json'
        os.link(self.sample,alias)
        with self.assertRaises(cli.RejectedInput):
            cli.read_verified_json(self.sample,self.sha)

    def test_duplicate_json_keys(self):
        raw=b'{"name":"ok","name":"overwrite"}'
        self.sample.write_bytes(raw)
        with self.assertRaises(cli.RejectedInput):
            cli.read_verified_json(self.sample,hashlib.sha256(raw).hexdigest())

    def test_oversized_input_rejected(self):
        self.sample.write_bytes(b'x'*(cli.MAX_FILE_BYTES+1))
        with self.assertRaises(cli.RejectedInput):
            cli.read_verified_json(self.sample,hashlib.sha256(self.sample.read_bytes()).hexdigest())

    def test_exclusive_output(self):
        target=self.dir/'out.json'
        digest=cli.write_exclusive(target,{'SPDXID':'SPDXRef-DOCUMENT'})
        self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),digest)
        if os.name != 'nt':
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
        else:
            self.assertTrue(target.exists())
        with self.assertRaises(FileExistsError):
            cli.write_exclusive(target,{'x':1})

    def test_missing_purl_rejected(self):
        doc=original.doc('missing-purl',
             [{'SPDXID':'SPDXRef-A','name':'no-purl','downloadLocation':'NOASSERTION'}],
             [original.rel('SPDXRef-DOCUMENT','SPDXRef-A','DESCRIBES')])
        class EmptyValidator:
            def iter_errors(self,doc):return []
        self.assertIn('package missing PURL; identity cannot be mapped',
                      cli.input_issues(doc,EmptyValidator()))


class RealPatchedMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.schema,cls.mod,cls.patch=load_patched(Path(cls.tmp.name))
        cls.v=jsonschema.Draft201909Validator(cls.schema)
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_clean(self):
        label,base,source,_=original.scenarios()[0]
        old=copy.deepcopy(base)
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual((verdict,issues),('ACCEPT',[]))
        self.assertEqual(base,old)
        self.assertEqual(list(self.v.iter_errors(result)),[])

    def test_wrong_parent_repaired(self):
        _,base,source,_=original.scenarios()[1]
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual((verdict,issues),('ACCEPT',[]))
        rels={(r['spdxElementId'],r['relatedSpdxElement'],r['relationshipType'])
              for r in result['relationships']}
        self.assertIn(('SPDXRef-Lib','SPDXRef-Leaf','DEPENDS_ON'),rels)
        self.assertNotIn(('SPDXRef-Main','SPDXRef-Leaf','DEPENDS_ON'),rels)

    def test_conflict_requires_review(self):
        _,base,source,_=original.scenarios()[2]
        old=copy.deepcopy(base)
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual(verdict,'REVIEW_REQUIRED')
        self.assertIsNone(result)
        self.assertEqual(base,old)

    def test_identity_collision_fails_closed(self):
        _,base,source,_=original.scenarios()[3]
        old=copy.deepcopy(base)
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual(verdict,'REJECT')
        self.assertIn('duplicate_spdxid',issues)
        self.assertIsNone(result)
        self.assertEqual(base,old)

    def test_external_doc_fails_closed(self):
        _,base,source,_=original.scenarios()[4]
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual(verdict,'REJECT')
        self.assertIsNone(result)

    def test_schema_invalid_input_rejected(self):
        _,base,source,_=original.scenarios()[0]
        source['spdxVersion']='SPDX-6.6'
        verdict,result,issues,_=cli.decision(base,source,self.mod.merge_sbom,self.v)
        self.assertEqual(verdict,'REJECT')
        self.assertIsNone(result)


if __name__=='__main__':
    unittest.main(verbosity=2)
