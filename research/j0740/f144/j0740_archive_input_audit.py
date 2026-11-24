#!/usr/bin/env python3
"""Stream the public Salmi J0740 tar once; inventory X-PSI run inputs.

Does not run a posterior or extract large event/calibration arrays. The source
member byte checks correspond to the prior independent F31 archive scan.
"""
import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path, PurePosixPath

PREFIX = 'J0740_GAMMA_zenodo/STU/STU_NICER_XMM_hr/'
RUN = PREFIX + 'STU_outputs/run1_lp40k_Xse001_Dfix/'
EXPECTED = {
    PREFIX+'STU_modules/config.ini': '02592091e8c10d126b10070e0e33515a292d57d750c2a45d624065d056752ede',
    PREFIX+'STU_modules/CustomPrior_GLS_compressed_scaling_Dfix.py': 'ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93',
    PREFIX+'STU_modules/main_lp40k_Xse001_Dfix.py': '440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af',
    RUN+'out_': 'f20ae7db9550a9fd608542c1b43fc9534a3e396df7ef5c2dad66493793caa2de',
}
DATA_HINT = re.compile(r'(event|spectrum|background|response|\.rsp|\.rmf|\.arf|channel|attenuat|atmosphere|\.fits|\.evt)', re.I)
ARCHIVE_MD5 = '7792c92b9ae1fa404ae5bdd3920ce075'


class HashedReader:
    def __init__(self, source):
        self.source = source
        self.md5 = hashlib.md5()
        self.n = 0

    def read(self, amount=-1):
        data = self.source.read(amount)
        self.md5.update(data)
        self.n += len(data)
        return data

    def drain(self):
        for _ in iter(lambda: self.read(1024*1024), b''):
            pass


def audit(archive: Path, out: Path) -> dict:
    stdin_mode = str(archive) == '-'
    if not stdin_mode and not archive.is_file():
        raise FileNotFoundError(archive)
    out.mkdir(parents=True, exist_ok=True)
    extracted = out/'small_original_members'
    extracted.mkdir(exist_ok=True)
    found = {}
    candidates = []
    member_count = 0
    total_uncompressed = 0
    inventory = out/'archive_members.jsonl'
    raw = sys.stdin.buffer if stdin_mode else archive.open('rb')
    reader = HashedReader(raw)
    try:
      with inventory.open('w', encoding='utf-8') as listing, tarfile.open(fileobj=reader, mode='r|gz') as tar:
        for member in tar:
            if not member.isfile():
                continue
            member_count += 1
            total_uncompressed += member.size
            listing.write(json.dumps({'name':member.name,'size_bytes':member.size},ensure_ascii=False)+'\n')
            if DATA_HINT.search(member.name) and member.name.startswith(PREFIX):
                candidates.append({'name':member.name,'size_bytes':member.size})
            chosen = member.name in EXPECTED or (
                member.name.startswith(PREFIX+'STU_modules/') and
                (member.name.endswith('.py') or member.name.endswith('.ini')) and member.size < 2_000_000)
            if chosen:
                # Never trust archive member paths as output destinations.
                filename = PurePosixPath(member.name).name
                if filename in found and found[filename]['member'] != member.name:
                    raise ValueError('Duplicate extracted basename: '+filename)
                src = tar.extractfile(member)
                if src is None:
                    raise ValueError('Unreadable member: '+member.name)
                digest = hashlib.sha256()
                dest = extracted/filename
                with dest.open('wb') as f:
                    for chunk in iter(lambda: src.read(1024*1024), b''):
                        digest.update(chunk)
                        f.write(chunk)
                actual = digest.hexdigest()
                expected = EXPECTED.get(member.name)
                found[filename] = {'member':member.name,'size_bytes':member.size,
                                   'sha256':actual,'expected_sha256':expected,
                                   'source_match':actual == expected if expected else None}
                if expected and actual != expected:
                    raise ValueError('Original source SHA mismatch: '+member.name)
            if member_count % 5000 == 0:
                print('Inventoried', member_count, 'files', flush=True)
      reader.drain()
    finally:
      if not stdin_mode:
        raw.close()
    archive_md5 = reader.md5.hexdigest()
    if archive_md5 != ARCHIVE_MD5:
        raise ValueError('Compressed archive MD5 mismatch: '+archive_md5)
    missing = sorted(set(EXPECTED)-{x['member'] for x in found.values()})
    result = {'schema':'J0740_ORIGINAL_ARCHIVE_INPUT_AUDIT_V1',
              'archive_path':str(archive),'archive_compressed_bytes':reader.n,
              'archive_md5':archive_md5,'published_archive_md5':ARCHIVE_MD5,
              'members':member_count,'total_uncompressed_bytes':total_uncompressed,
              'original_member_sha256_checked':len(EXPECTED)-len(missing),
              'missing_expected_original_members':missing,'extracted_small_members':found,
              'data_input_candidates':candidates,'inventory_path':str(inventory),
              'status':'PASS_ORIGINAL_F31_SOURCE_MEMBERS' if not missing else 'INCOMPLETE_SOURCE_MEMBERS',
              'limitations':'Inventory only; no photon likelihood or seven-EOS evidence computed.'}
    (out/'source_input_audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'members':member_count,
                      'candidates':len(candidates),'extracted':len(found)},ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('archive',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    result=audit(a.archive,a.out)
    raise SystemExit(0 if not result['missing_expected_original_members'] else 2)
