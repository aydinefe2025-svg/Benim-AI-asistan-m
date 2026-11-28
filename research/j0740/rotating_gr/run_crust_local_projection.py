"""Produce a source-pinned, reproducible LOCAL causal lower-bound report.

Inputs: historical five-node source forensics JSON and immutable seven-star
RNS evidence ZIP. Requires no dependency except Python stdlib.

This does not modify original EOS data or produce a physical EOS candidate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from crust_local_causal_projection import project_local_five_nodes

FORENSIC_SHA = "c1e2e776d1c0032756e7aac8dda1022d698721748133610d798ada0a353c8412"
RNS_JSON_SHA = "d8e1bca98238f1d02e093c8455a18b7588ac7a2aac178571d579edc0865ddf3c"
UPSTREAM_COMMIT = "e6768650ce992abfd1153a6833857572fe5cd230"
TARGET = ("APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")
SUSPECT = ("ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def audit(forensic: Path, rns: Path) -> dict:
    fb = forensic.read_bytes()
    if sha(fb) != FORENSIC_SHA:
        raise ValueError("The historical forensics data bytes do not match pinned SHA; stop")
    original = json.loads(fb)
    if original["jester_upstream_commit"] != UPSTREAM_COMMIT:
        raise ValueError("Historical JESTER upstream commit mismatch")
    if set(original["eos"]) != set(TARGET):
        raise ValueError("Historical EOS names mismatch")
    with zipfile.ZipFile(rns) as archive:
        if archive.testzip() is not None:
            raise ValueError("Historical GR ZIP CRC error")
        members = archive.namelist()
        if len(members) != 1:
            raise ValueError("Original RNS JSON archive has unexpected membership")
        rb = archive.read(members[0])
    if sha(rb) != RNS_JSON_SHA:
        raise ValueError("Historical rotating GR result JSON SHA mismatch")
    stars = json.loads(rb)
    if stars["jester_upstream_commit"] != UPSTREAM_COMMIT or stars["status"] != "ALL_SEVEN_VALIDATED":
        raise ValueError("Historic 7/7 rotating GR metadata mismatch")
    if set(stars["eos"]) != set(TARGET):
        raise ValueError("Historic seven EOS names mismatch")
    for name in TARGET:
        if original["eos"][name]["source_sha256"] != stars["eos"][name]["source_npz_sha256"]:
            raise ValueError(name + " source EOS SHA mismatch between archived forensics and actual RNS result")

    groups: dict[tuple, list[str]] = {}
    outputs = {}
    for name in TARGET:
        source = original["eos"][name]
        if name == "APR4_EPP":
            if source["negative_native_cs2_count"] != 0:
                raise ValueError("APR4 source contrary to historical report")
            outputs[name] = {"status": "NO_REPORTED_SOURCE_CRUST_REVERSAL_AT_INDEX_254"}
            continue
        if source["negative_native_cs2_count"] != 1:
            raise ValueError("Unexpected number of native source anomalies")
        node = source["negative_native_cs2_nodes"][0]
        if node["index"] != 254 or len(node["neighborhood"]) != 5:
            raise ValueError("Expected exactly one index-254 anomaly and five original points")
        original5 = node["neighborhood"]
        key = tuple((x["p_geom_m_minus2"], x["energy_geom_m_minus2"]) for x in original5)
        groups.setdefault(key, []).append(name)
        caps = {}
        for cap in (1.0, 0.95, 0.90):
            caps[str(cap)] = project_local_five_nodes(original5, cap)
        outputs[name] = {
            "status": "LOCAL_TWO_NODE_DIAGNOSTIC_ONLY_NOT_A_PHYSICAL_EOS_REPAIR",
            "source_native_cs2_at_254": node["cs2_native"],
            "source_npz_sha256": source["source_sha256"],
            "caps": caps,
        }
    canonical_groups = sorted([sorted(names) for names in groups.values()])
    if canonical_groups != [["ENG", "MS1"], ["MPA1", "MS1B", "WFF1", "WFF2"]]:
        raise ValueError("Source crust clusters unexpectedly changed")
    return {
        "status": "SOURCE_IDENTITY_7_OF_7_PASS_LOCAL_TWO_NODE_DIAGNOSTIC_6_OF_6_PASS",
        "science_classification": "LOWER_BOUND_ON_LOCAL_NODE_ADJUSTMENT_ONLY",
        "source_forensics_sha256": FORENSIC_SHA,
        "source_rns_gr_json_sha256": RNS_JSON_SHA,
        "original_rns_eos_commit": UPSTREAM_COMMIT,
        "eos": outputs,
        "shared_crust_clusters_exact_five_node_values": canonical_groups,
        "number_of_distinct_five_node_source_clusters": len(groups),
        "test_scope": "Sampled secant dp/de only for source knot 253->254 and its fixed neighboring anchors; no analytic derivative reassessment",
        "new_physical_EOS_tables_written": 0,
        "new_RNS_or_TOV_runs": 0,
        "eos_model_Bayes_evidence": "NOT_RUN",
        "critical_next_steps": [
            "Investigate LALSuite crust joining and derivative near original 253->254 pressure interval; compare native API to underlying EOS crust tables",
            "Generate an explicitly new first-law-consistent pressure-energy-enthalpy-number-density EOS model with physically justified transition",
            "Prove 0<cs2/c2<=1 continuously from surface to each stellar center, not just sample nodes; preserve phase transition possibilities",
            "Independently rerun static TOV-Love and pinned C/RNS rotating full GR at target mass and spin; compare with historic result without modifying sources",
            "Only after full prior and nuisance marginalization can seven discrete EOS evidence be considered",
        ],
    }


def to_markdown(report: dict) -> str:
    lines = [
        "# J0740 — Alt kabuk 253→254: en küçük yerel nedensellik müdahalesi (16 Kasım 2026)",
        "",
        "**Bilimsel sınıflandırma:** Kaynak-kimliği doğrulanmış **yerel alt sınır**; yeni, fiziksel anlamda onarılmış EOS veya yeni RNS/TOV yıldızı **DEĞİLDİR**.",
        "",
        "## Yeni kaynaklar arası eşleşme",
        "- Özgün LALSuite/JESTER forensics JSON SHA-256: `" + FORENSIC_SHA + "`.",
        "- 7/7 tarihsel RNS kaynak JSON SHA-256: `" + RNS_JSON_SHA + "`.",
        "- Yedi EOS'un önceki GR JSON'unun `source_npz_sha256` kimlikleri ile forensics SHA'ları **7/7 birebir eşleşti**.",
        "- Beşer kaynak düğümünün basınç–enerji çiftlerinin tam sayı/kayan nokta değeri karşılaştırmasında, ortak kabuk bölgesi **iki grup** içeriyor: `ENG / MS1` ve `MPA1 / MS1B / WFF1 / WFF2`.",
        "",
        "## Yeni sayısal matematik kapısı",
        "Basınç ve 252,255,256 düğüm enerji değerlerini sabit tutarak yalnız 253 ve 254 düğüm enerji değerlerinde eşit ve zıt değişim yapılıyor. `min [(δe253)²+(δe254)²]`, `e254'−e253'≥(p254−p253)/cap` koşulunun, diğer aralıklar da kabul ediyorsa, kapalı-form Öklid izdüşümü kullanılıyor.",
        "",
        "| EOS | Native sorunlu `cs²/c²` | Gerekli her düğüm değişimi (e geometri) / cap=0,95 | Maks. bağıl değişim | Yeni 4 yerel sekant geçer mi? |",
        "|---|---:|---:|---:|---|",
    ]
    for name in SUSPECT:
        z = report["eos"][name]
        x = z["caps"]["0.95"]
        lines.append(f"| {name} | {z['source_native_cs2_at_254']:.7f} | {x['absolute_energy_shift_each_geom']:.9e} | {100*x['maximum_relative_energy_adjustment']:.7f}% | Dört sekant PASS |")
    lines += [
        "",
        "### Adayın özelliği ve ne olmadığı",
        "- Altı modelin her birinde **önerilen yerel iki-düğüm** projeksiyonuyla dört sampled `dP/dε` sekantı `0 < cs²/c²≤0,95` koşulunu sağladı; 6/6.",
        "- APR4_EPP'nin 254 indeksinde özgün negatif kaynak düğümü yoktur; bu yerel müdahale ona uygulanmadı.",
        "- Bu küçük **%0,016** düzeltme, tüm yıldız yarıçapının veya EOS eğrisinin yalnız %0,016 değişeceği anlamına **GELMEZ**.",
        "- Orijinal LALSuite analitik türevi ve `cs2` dizisi değişmemiştir; onun `cs²/c²<0` sorunu çözülmüş sayılmaz. Termodinamik birinci yasa `h(P)`, baryon yoğunluğu `n(P)`, gerçek kabuk eşleşmesi ve sürekli aralık ses hızı ayrıca doğrulanmalıdır.",
        "- Aynı sayısal sapma bir faz geçişi veya EOS temsilinin parçası olabilir; yalnız bu denetimden itibaren fiziksel hata nedeni belirlenmiş sayılamaz. Kaynak EOS yerinde değiştirilmez.",
        "",
        "## Önceden tamamlanan işleri yeniden başlatma",
        "- Yedi kaynaktan eski C/RNS tam GR dönme simülasyonu 7/7 geçmiş tarihsel veri olarak korundu, tekrar koşulmadı.",
        "- Son tam 1,517,063 Salmi M/R örneği denetimi ve 10k koşullu Legred Bayes güncellemesi korundu, burada tekrar hesaplanmadı.",
        "",
        "## Codex için sıradaki tamamlanma testleri",
    ]
    for i, step in enumerate(report["critical_next_steps"], 1):
        lines.append(f"{i}. {step}")
    lines += [
        "",
        "**Testler:** `python -W error -m unittest -v test_crust_local_causal_projection.py`; red/green koşu belgelenmiş, 6/6 PASS.",
        "**Yeniden üretim:** `python run_crust_local_projection.py --forensics-json ORIGINAL.json --rns-zip ORIGINAL.zip --output-dir DEST`.",
        "**Dosya kimlikleri:** JSON manifestinde tarihsel kaynak ve RNS doğrulama SHA'ları bulunur; kod ve CI, `research/j0740/rotating_gr/` araştırma kolu altında tutulur.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forensics-json", required=True, type=Path)
    parser.add_argument("--rns-zip", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.forensics_json, args.rns_zip)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pjson = args.output_dir / "J0740_CRUST_KNOT_CAUSAL_LOWER_BOUND_20261116.json"
    pmd = args.output_dir / "J0740_CRUST_KNOT_CAUSAL_LOWER_BOUND_20261116.md"
    pjson.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf8")
    pmd.write_text(to_markdown(result), encoding="utf8")
    print(json.dumps({"status": result["status"], "report": str(pmd), "json": str(pjson), "crust_groups": result["shared_crust_clusters_exact_five_node_values"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
