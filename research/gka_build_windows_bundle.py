#!/usr/bin/env python3
"""Package only minimal standard-library replay sources; never package raw telemetry."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    "research/gka_final_owner_replay.py",
    "research/test_gka_final_owner_replay.py",
    "research/tsuru_agv_real_source_ci.py",
    "research/birds_eps_constellation_qc.py",
    "research/birds_manuscript_population_guard.py",
    "research/birds_published_panel_rules.py",
    "research/agv_temp_stratified_qc.py",
    "research/agv_day_cluster_common_support.py",
    "research/agv_month_pair_block_sensitivity.py",
    "research/test_birds_manuscript_population_guard.py",
    "research/test_birds_published_panel_rules.py",
    "research/test_agv_temp_stratified_qc.py",
    "research/test_agv_day_cluster_common_support.py",
    "research/test_agv_month_pair_block_sensitivity.py",
    "scripts/GKA_FINAL_WINDOWS.ps1",
)
README = """# Kuresel Kesif Agi - Windows tek komut bilimsel dogrulama

Bu paket, TSURU / UGUISU / RAAVANA / NEPALISAT EPS ve on adet AGV
batarya operasyonel kaydini orijinal yayinci kaynagindan tekrar hesaplar.
NicER EOS 12,9 GB dosyasi ile HICBIR ilgisi yoktur. Herhangi bir veri
yedegini veya mevcut bilgisayar dosyasini degistirmez.

Gerekli: Windows PowerShell 7 / pwsh, Python 3.11+, internet (GitHub,
Zenodo). Ucretli API anahtari veya ekstra pip paketi gerekmez.
Bazi GitHub API kota sinirlarinda kaynak erisimi basarisiz olabilir;
bu durum dogrulama basarisi degil, ACIK basarisizlik raporu verir.

Adim 1: ZIP'i yeni bir klasore cikart.
Adim 2: O klasorde PowerShell 7 ile sunu calistir:
    pwsh -NoProfile -File .\\scripts\\GKA_FINAL_WINDOWS.ps1

Alternatif:
    python .\\research\\gka_final_owner_replay.py --output-dir .\\KANITIM

Bitti denmesi icin GKA_FINAL_REPLAY_STATUS.json dosyasinda
COMPUTATIONAL_ORIGINAL_SOURCE_REPLAY_VERIFIED yazmali.
Cikti klasorunde 7 kaynak JSON makbuzu, loglar, bir kontrol manifesti,
ve GKA_FINAL_PROOF.zip olusur. Basarisizlikta ZIP URETILMEZ.
Kaynagin MD5/SHA, satirlar, 4 uydu ve 2022 yayin orneklem farki
ile AGV ay ciftleri hesaplari capraz denetlenir.

Bilimsel sinir: Bu sonuc agv kapasite/SoH, fiziksel ariza, nedensel
yaslanma veya yayindaki etiketli benchmarkin yeniden uretilmesi DEGILDIR.
"""

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    archive=output/"GKA_WINDOWS_LOCAL_BUNDLE.zip"
    if archive.exists():
        raise ValueError("Refuse to overwrite existing owner handoff bundle")
    files={}
    for rel in FILES:
        data=(ROOT/rel).read_bytes()
        files[rel]={"sha256":hashlib.sha256(data).hexdigest(),"size":len(data)}
    rev=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    manifest={"bundle_code_commit":rev,"files":files,
              "raw_data_included":False,"license_note":"Only replay orchestration code; original datasets fetched separately from pinned publishers"}
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for rel in FILES:
            z.write(ROOT/rel,rel)
        z.writestr("README_BASLA.md",README)
        z.writestr("SOURCE_CODE_SHA256_MANIFEST.json",json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist()) != set(FILES)|{"README_BASLA.md","SOURCE_CODE_SHA256_MANIFEST.json"}:
            raise RuntimeError("owner ZIP CRC or membership failure")
    print("WINDOWS_PORTABLE_BUNDLE_VERIFIED="+json.dumps({"path":str(archive),"bytes":archive.stat().st_size,
          "sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
          "code_files":len(FILES),"repo_commit":rev},sort_keys=True))

if __name__=="__main__":
    main()
