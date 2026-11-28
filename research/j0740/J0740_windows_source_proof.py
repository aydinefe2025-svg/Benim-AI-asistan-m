"""One-command, non-destructive Windows proof runner for already-owned J0740 archive.

No 12.9 GB download, no full extraction, no public upload. Pinned GitHub code
is authenticated via Git blob SHA-1 (repository integrity identity), and the
source scanner checks full compressed-archive MD5 plus member SHA-256.

Run from this directory with: py -3 J0740_windows_source_proof.py
Optional: py -3 J0740_windows_source_proof.py --archive C:\\path\\to\\existing.tar.gz
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import Request, urlopen

ARCHIVE_FILENAME = 'psr_J0740+6620_with_3p6_Years_of_NICER_Data.tar.gz'
ARCHIVE_MD5 = '7792c92b9ae1fa404ae5bdd3920ce075'
PINNED_COMMIT = '9c19262238fdf790eb2d0e71e71e5e2496c96086'
PINNED_BLOBS = {
    'source_lineage_gate.py': '3500b497369a06c039b7c4769e6a9dfb7ba60418',
    'original_salmi_run_probe.py': 'b3b8057e64afe53d53397ba780718b0332ea4a0a',
}
REPO_SLUG = 'aydinefe2025-svg/Benim-AI-asistan-m'


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f'blob {len(data)}\0'.encode('ascii') + data).hexdigest()


def locate_archive(explicit: str | None, home: Path) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f'Belirtilen mevcut arşiv yok: {p}')
    env = os.environ.get('J0740_ARCHIVE_PATH')
    if env:
        p=Path(env).expanduser()
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(f'J0740_ARCHIVE_PATH mevcut bir dosya değil: {p}')
    candidates=[]
    for root in (home/'Downloads', home/'Desktop', home/'Documents'):
        if root.is_dir():
            exact=root/ARCHIVE_FILENAME
            if exact.is_file(): candidates.append(exact)
            else: candidates.extend(root.glob(f'**/{ARCHIVE_FILENAME}'))
    # Never pick an arbitrary tar.gz and never guess which archive is correct.
    unique=sorted(set(p.resolve() for p in candidates))
    if len(unique)==1: return unique[0]
    if not unique:
        raise FileNotFoundError('Yerel Salmi arşivi bulunamadı. --archive ile mevcut yolunu belirt; yeniden indirme yok.')
    raise ValueError('Birden çok aynı isimli arşiv var; güvenle seçmek için --archive belirt: '+str(unique))


def repo_candidates(home: Path, bundle: Path, source_code_dir: Path | None = None):
    if source_code_dir is not None:
        yield source_code_dir
    # Use an existing local GitHub checkout before attempting tiny source downloads.
    yield bundle
    yield home/'Benim-AI-asistan-m'/'research'/'j0740'
    yield home/'Documents'/'GitHub'/'Benim-AI-asistan-m'/'research'/'j0740'
    yield home/'source'/'repos'/'Benim-AI-asistan-m'/'research'/'j0740'


def pinned_code(name: str, home: Path, bundle: Path, source_code_dir: Path | None = None) -> bytes:
    expected = PINNED_BLOBS[name]
    for root in repo_candidates(home, bundle, source_code_dir):
        file=root/name
        if file.is_file():
            data=file.read_bytes()
            if git_blob_sha(data)==expected:
                return data
    # Only two small Python source files; NEVER download the large 12.9GB archive.
    url=f'https://raw.githubusercontent.com/{REPO_SLUG}/{PINNED_COMMIT}/research/j0740/{name}'
    with urlopen(Request(url,headers={'User-Agent':'J0740-source-proof/1'}),timeout=30) as stream:
        data=stream.read(200_001)
    if len(data)>200_000 or git_blob_sha(data)!=expected:
        raise ValueError(f'Kaynak kod Git blob kimliği eşleşmedi: {name}')
    return data


def public_summary(report: dict) -> dict:
    # No source-code bytes, secrets, full log, or local filesystem paths.
    return {
        'schema':'A01.01.51-original-archive-source-proof-summary-v1',
        'source_full_archive_md5_expected':ARCHIVE_MD5,
        'source_full_archive_md5_observed':report.get('source_full_archive_md5_observed_this_scan'),
        'source_full_archive_sha256_observed':report.get('source_full_archive_sha256_observed_this_scan'),
        'compressed_archive_checksum_verified':report.get('compressed_archive_checksum_verified',False),
        'strict_lineage_verified':report.get('strict_lineage_verified',False),
        'lineage_gate_status':report.get('lineage_gate_status'),
        'issues':report.get('issues',[]),
        'original_members':{
            role:{k:data.get(k) for k in ('sha256','actual_tar_member_name','bytes','status')}
            for role,data in report.get('selected',{}).items()},
        'scientific_status':'SOURCE_PROVENANCE_ONLY; NO_NATIVE_PHOTON_LIKELIHOOD_OR_EOS_BAYES_POSTERIOR',
    }


def run(*, archive: Path, home: Path, bundle: Path, output: Path, source_code_dir: Path | None = None):
    archive = archive.resolve()
    output=output.resolve()
    if output == archive.parent or output==archive or archive.is_relative_to(output):
        raise ValueError('Kanıt klasörü kaynak arşivin kendisi veya üst klasörü olamaz')
    output.mkdir(parents=True,exist_ok=True)
    code_dir=output/'pinned_scanner'
    code_dir.mkdir(exist_ok=True)
    for name in PINNED_BLOBS:
        data=pinned_code(name,home,bundle,source_code_dir)
        (code_dir/name).write_bytes(data)
    probe=output/'probe'
    print('Mevcut arşivin özgün kimliği ve dört kaynak dosyası kontrol ediliyor; yeni veri indirilmiyor.')
    result=subprocess.run([sys.executable,str(code_dir/'original_salmi_run_probe.py'),
         '--archive',str(archive),'--out',str(probe)],text=True,stdout=subprocess.PIPE,
         stderr=subprocess.STDOUT,timeout=7200)
    report_path=probe/'source_run_probe_report.json'
    if not report_path.is_file():
        raise RuntimeError('Tarayıcı sonuç JSON üretmedi (işlem tamamlanmamış): '+result.stdout[-1500:])
    report=json.loads(report_path.read_text(encoding='utf-8'))
    summary=public_summary(report)
    (output/'share_only_this_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'result':('VERIFIED_SOURCE_ONLY' if summary['strict_lineage_verified']
                       else 'NOT_VERIFIED'), 'summary':str(output/'share_only_this_summary.json'),
                       'issues':summary['issues'],'scanner_exit_code':result.returncode},ensure_ascii=False))
    # Provenance only; photon likelihood / EOS model evidence remain uncomputed.
    if result.returncode or not summary['strict_lineage_verified']:
        raise SystemExit(2)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',help='The original already-downloaded 12.9GB tar.gz file')
    p.add_argument('--output',type=Path,help='Destination for four tiny extracted proof files')
    p.add_argument('--source-code-dir',type=Path,help='Existing local research/j0740 folder if repository is private')
    args=p.parse_args()
    home=Path.home()
    out=args.output or home/'Documents'/'A01.01.50'/'PSR_J0740+6620'/'04_validation_reports'/'original_source_proof'
    archive=locate_archive(args.archive,home)
    run(archive=archive,home=home,bundle=Path(__file__).resolve().parent,output=out,source_code_dir=args.source_code_dir)

if __name__=='__main__':
    try: main()
    except (FileNotFoundError,ValueError,RuntimeError) as e:
        print('KAYNAK KANITI TAMAMLANMADI:',e,file=sys.stderr)
        raise SystemExit(2)