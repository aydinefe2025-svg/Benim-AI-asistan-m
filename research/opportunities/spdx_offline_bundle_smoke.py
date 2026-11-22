#!/usr/bin/env python3
"""Independent, no-network test of the downloaded portable SPDX CLI bundle."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

import spdx_upstream_acceptance as inputs


def run():
    archive=Path('spdx-secure-pilot.zip')
    with tempfile.TemporaryDirectory(prefix='cano-spdx-offline-smoke-') as d:
        folder=Path(d)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            z.extractall(folder)
        manifest=json.loads((folder/'MANIFEST.json').read_text(encoding='utf8'))
        assert manifest['offline_pinned_vendor']
        for name,expected in manifest['source_and_schema_sha256'].items():
            digest=hashlib.sha256((folder/name).read_bytes()).hexdigest()
            assert digest==expected, f'bad SHA256: {name}'
        label,base,source,_=inputs.scenarios()[1]  # wrong parent, now repaired
        args=[]
        for name,doc in (('base',base),('source',source)):
            path=folder/f'{name}.spdx.json'
            raw=(json.dumps(doc,ensure_ascii=False)+'\n').encode('utf8')
            path.write_bytes(raw)
            args += [f'--{name}',str(path),f'--{name}-sha256',
                     hashlib.sha256(raw).hexdigest()]
        env=os.environ.copy()
        env['CANO_OFFLINE_ONLY']='1'
        output=folder/'merged.spdx.json'
        cmd=[sys.executable,str(folder/'spdx_secure_merge_cli.py'),
             *args,'--output',str(output)]
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=40,env=env)
        assert done.returncode==0,(done.stdout,done.stderr)
        receipt=json.loads(done.stdout)
        assert receipt['status']=='ACCEPT'
        assert receipt['source_mode']=='offline_pinned_vendor'
        assert receipt['output_written'] and output.exists()
        merged=json.loads(output.read_text(encoding='utf8'))
        edges={(x['spdxElementId'],x['relatedSpdxElement'],x['relationshipType'])
               for x in merged['relationships']}
        assert ('SPDXRef-Lib','SPDXRef-Leaf','DEPENDS_ON') in edges
        assert ('SPDXRef-Main','SPDXRef-Leaf','DEPENDS_ON') not in edges
        # The exclusive-create guarantee must prevent silent overwrites.
        again=subprocess.run(cmd,capture_output=True,text=True,timeout=40,env=env)
        assert again.returncode==2
        assert hashlib.sha256(output.read_bytes()).hexdigest()==receipt['output_sha256']
        # Byte tampering with an offline vendored original is rejected before import.
        vendored=folder/'vendor/src/sbom_unifier/merge/merger.py'
        vendored.write_bytes(vendored.read_bytes()+b'\n# tampered\n')
        tamper_output=folder/'tampered.spdx.json'
        bad_cmd=[*cmd[:-1],str(tamper_output)]
        bad=subprocess.run(bad_cmd,capture_output=True,text=True,timeout=40,env=env)
        assert bad.returncode==2,(bad.stdout,bad.stderr)
        assert not tamper_output.exists()
        print(json.dumps({'bundle_manifest_files':len(manifest['source_and_schema_sha256']),
                          'offline_cli_merge':'PASS',
                          'correct_parent_edge':'PASS',
                          'exclusive_output':'PASS',
                          'tampered_vendor_rejected':'PASS',
                          'online_requests_required':False},ensure_ascii=False))


if __name__=='__main__':
    run()
