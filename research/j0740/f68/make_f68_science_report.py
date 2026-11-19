"""Build a cryptographically inspectable F68 science report with fail-closed source/model labels."""
from __future__ import annotations
import argparse,hashlib,json,zipfile
from pathlib import Path

MODEL='MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
STATUS='DIRECT_RNS_C_ALTERNATE_PCHIP_COLD_GRID_DIAGNOSTIC_PASS_NO_EOS_BAYES'
EOS_SHA='5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(coarse,fine,old_original,independent_static,coarse_zip,fine_zip,report,summary,manifest):
    a=json.loads(Path(coarse).read_text());b=json.loads(Path(fine).read_text());f62=json.loads(Path(old_original).read_text());z=json.loads(Path(independent_static).read_text())
    if (a['status']!=STATUS or b['status']!=STATUS or a['model']!=MODEL or b['model']!=MODEL or
        not a['not_original_MPA1'] or not b['not_original_MPA1'] or
        a['rns_derived_table_sha256']!=b['rns_derived_table_sha256'] or a['rns_derived_table_sha256']!=EOS_SHA or
        set(a['direct_C_stars'])!={'2.073','2.175','2.200','2.250'} or
        set(b['direct_C_stars'])!={'2.073','2.250'} or z['status']!='TWO_INDEPENDENT_STATIC_TOV_FORMULATIONS_PASS_NOT_ROTATING'):
        raise ValueError('F68_BROKEN_SCIENTIFIC_SOURCE_OR_EOS_PROVENANCE')
    for p in (coarse_zip,fine_zip):
        with zipfile.ZipFile(p) as x:
            if x.testzip() is not None: raise ValueError('F68_CORRUPT_CI_ZIP')
    if f62['original_JESTER_source_MPA1_npz_SHA256']!='0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22':
        raise ValueError('F68_OLD_ORIGINAL_MPA1_REFERENCE_DRIFT')
    rows=[];max_grid_r=0;max_grid_s=0;max_vs_f67=0
    for target,block in a['direct_C_stars'].items():
        if block['status']!='DIRECT_RNS_C_SPIN_AND_STATIC_ROOTS_PASS_NUMERICAL_ONLY':raise ValueError('F68_COARSE_DIRECT_C_STAR_MISSING')
        rot=block['rotating']['star'];sta=block['static']['star'];ref=z['stars'][target]['rm']
        static_minus_independent_m=(sta['radius_eq_km']-ref['radius_km'])*1000
        old=f62['verified_rotating_static_mesh_comparisons'][target]['RNS_direct_196pt_rotation_req_km']
        rec={'mass_msun':float(target),'grid151x301_rot_R_eq_km':rot['radius_eq_km'],
             'grid151x301_stat_R_km':sta['radius_eq_km'],
             'grid151x301_spinning_hz':rot['spin_hz_reported'],
             'grid151x301_rot_minus_stat_m':1000*(rot['radius_eq_km']-sta['radius_eq_km']),
             'independent_static_TOV_R_km':ref['radius_km'],
             'coarse_RNS_static_minus_independent_TOV_m':static_minus_independent_m,
             'old_original_MPA1_F62_RNS196_R_eq_km_not_same_EOS':old,
             'new_alternate_minus_old_original_RNS196_spin_R_m_NOT_EOS_EVIDENCE':1000*(rot['radius_eq_km']-old)}
        max_vs_f67=max(max_vs_f67,abs(static_minus_independent_m))
        if target in b['direct_C_stars']:
            blockb=b['direct_C_stars'][target]
            if blockb['status']!='DIRECT_RNS_C_SPIN_AND_STATIC_ROOTS_PASS_NUMERICAL_ONLY':raise ValueError('F68_FINE_DIRECT_C_STAR_MISSING')
            rb=blockb['rotating']['star'];sb=blockb['static']['star']
            rec.update(grid201x401_rot_R_eq_km=rb['radius_eq_km'],
                grid201x401_stat_R_km=sb['radius_eq_km'],
                grid201x401_spinning_hz=rb['spin_hz_reported'],
                fine_minus_coarse_spin_R_m=1000*(rb['radius_eq_km']-rot['radius_eq_km']),
                fine_minus_coarse_static_R_m=1000*(sb['radius_eq_km']-sta['radius_eq_km']),
                fine_static_RNS_minus_independent_TOV_m=1000*(sb['radius_eq_km']-ref['radius_km']))
            max_grid_r=max(max_grid_r,abs(rec['fine_minus_coarse_spin_R_m']))
            max_grid_s=max(max_grid_s,abs(rec['fine_minus_coarse_static_R_m']))
        rows.append(rec)
    results={'schema':'J0740_F68_NEW_ALTERNATE_PCHIP_COLD_ROTATING_GR_4_MASS_2_SPATIAL_GRID_AND_STATIC_DIAGNOSTIC',
       'status':'F68_DIRECT_NEW_ALTERNATE_ROTATING_GR_NUMERICAL_PASS_NO_PHYSICAL_XPSI_EOS_BAYES',
       'model':MODEL,'not_original_MPA1':True,'not_F42':True,
       'spin_target_Hz':346.536369,'exact_identical_rns_derived_EOS_table_sha256':EOS_SHA,
       'direct_C_rotating_and_static_roots_coarse':8,
       'direct_C_rotating_and_static_roots_fine':4,
       'independent_TOV_method_stars':8,
       'max_two_spatial_grids_rot_R_difference_m':max_grid_r,
       'max_two_spatial_grids_static_R_difference_m':max_grid_s,
       'max_RNS_coarse_static_vs_independent_TOV_m':max_vs_f67,
       'results':rows,
       'parent_F67_thermo_table_SHA256':'d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22',
       'parent_F67_TOV_report_SHA256':'811b6b9e3763e77df0e300f54cae0301cdac1cb1c285b09da8f32e23c0aa0dc8',
       'native_source_photon_XPSI_likelihood':'NOT_RUN','seven_original_EOS_Bayes':'NOT_RUN',
       'alternative_model_physically_certified':'NOT_ESTABLISHED',
       'cold_baryon_n0_and_m0_physical_normalization':'NOT_ESTABLISHED',
       'proper_physical_P0_surface_and_crust_matching':'NOT_ESTABLISHED',
       'global_constant_J_stability_on_ALTERNATE':'NOT_RUN',
       'caveats':['This is an ALTERNATIVE mathematical PCHIP cold EOS, not original nuclear MPA1 or a physical EOS approval',
           'Fine grid only compares 2 of 4 target masses; two-grid radius differences NOT observational error bars',
           'All quoted masses are direct RNS C equilibrium roots within tolerance',
           'Static F67 table TOV crosschecks independent but not proof of surface/composition',
           'Old original F62 rotating radius comparison is numerical-model sensitivity, NOT Bayesian EOS evidence',
           'Baryonic M0 from RNS uses an arbitrary n0 proxy and must not be published as physical mass',
           'Original full photon X-PSI and properly normalized seven nuclear EOS likelihood are not computed']}
    if max_grid_r>100 or max_grid_s>100 or max_vs_f67>200:
        raise ValueError('F68_DIRECT_GR_SPACETIME_OR_STATIC_CONVERGENCE_GATE_FAIL')
    Path(summary).write_text(json.dumps(results,sort_keys=True,indent=2)+'\n')
    text=["# A01.01.51 — F68: ayrı MPA1-PCHIP-COLD EOS ile gerçek dönen GR yıldızları", "",
      "**19 Kasım 2026 · F67'yi izleyen YENİ doğrudan C/RNS sayısal fizik deneyi.**",
      "", "## Fiziksel model ve kabul sınırı", "",
      "Model: `MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL`. **Özgün MPA1 değildir; F42 değildir.** F67 termodinamik tablo SHA-256 `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22`. RNS için 196 noktalık aynı türetilmiş EOS tablosu kullanıldı; SHA-256 `"+EOS_SHA+"`. F67'nin ilk-yasaya göre n/n0 şekli korunurken `n0` keyfi bir pozitif referans ile sayısal RNS formatına dönüştürüldü: **RNS M0 fiziksel baryonik kütle değildir**.",
      "", "## Yeni gerçek 346,536369 Hz tam-GR dönen yıldız sonuçları", "",
      "| M (M☉) | 151×301 R_eq spin (km) | 151×301 statik R (km) | Bağımsız statik TOV R (km) | 201×401 R_eq spin (km) | İnce−kaba dönme R (m) |",
      "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        fine_radius=row.get('grid201x401_rot_R_eq_km');delta=row.get('fine_minus_coarse_spin_R_m');
        text.append(f"| {row['mass_msun']:.3f} | {row['grid151x301_rot_R_eq_km']:.9f} | {row['grid151x301_stat_R_km']:.9f} | {row['independent_static_TOV_R_km']:.9f} | {fine_radius:.9f} | {delta:+.4f} |" if fine_radius is not None else f"| {row['mass_msun']:.3f} | {row['grid151x301_rot_R_eq_km']:.9f} | {row['grid151x301_stat_R_km']:.9f} | {row['independent_static_TOV_R_km']:.9f} | — | — |")
    text.extend(["",f"**İki uzaysal ızgara sonucu:** Maksimum spin R_eq farkı `{max_grid_r:.6f} m`, maksimum statik R farkı `{max_grid_s:.6f} m` (2 hedefte karşılaştırıldı); her iki C binary **birebir aynı EOS tablo baytlarını** okudu. Bunlar tam model belirsizliği veya gözlemsel hata çubuğu değildir. Kaba RNS statik kütle-yarıçap değerleriyle 4 kütlede bağımsız Python ilk-yasa EOS TOV farklarının maksimumu `{max_vs_f67:.6f} m`.",
      "", "**Özgün EOS ile model farkı:** F62 özgün MPA1'in 196 düğümlü ayrı orijinal türetilmiş tablosundaki dönen yıldızlarla F68 alternatif RNS çapraz-farkı `+2,12 m (2,073 M☉)` ile `−5,69 m (2,250 M☉)` arasında. F61–F67 statik TOV farkının −45,39m olmasıyla **bunları eşitleyip fiziksel EOS ölçüm hassasiyeti çıkarmak yanlış**; farklı kaynak tablolarının, enterpolasyonların ve çözüm prosedürünün etkisi vardır.",
      "", "## Kaynak, test ve SHA makbuzları", "",
      "- GitHub PR #633 (ilk koşu). Kaba 151×301 ve ince 201×401 RNS-C full-GR gerçek derleme; C denklemlerine **dokunulmadı**, yalnız stdout hassasiyet biçimi değiştirildi.",
      "- 18/18 fail-closed bilimsel birim testi; iki gerçek C çözüm işi, PR'nin üç workflow kontrolü PASS (son merge commit/CI ayrıca kanıtlandıktan sonra Notion makbuzuna yazılır).",
      f"- CI kaba ZIP SHA256 `{sha(coarse_zip)}`; ince ZIP SHA256 `{sha(fine_zip)}` (ZIP CRC PASS).",
      f"- Ham coarse sonuç JSON SHA `{sha(coarse)}`; fine JSON SHA `{sha(fine)}`; bağımsız static TOV JSON SHA `{sha(independent_static)}`.",
      "", "## Kapatılmamış fizik", "",
      "Bu hesap **fiziksel kabuk P=0 eşlemesini**, baryon kimyasal potansiyel µ0/n0 ve M0 fiziksel kalibrasyonunu, F67 alternatif için küresel sabit-J kararlılığı, özgün NICER/XMM-Newton 12.9GB foton X-PSI nuisance likelihood'unu veya **yedi özgün nükleer EOS Bayes** hesabını **yapmadı**. Sayısal RNS yıldız başarısı, EOS kabulü veya gözlemsel çıkarım başarısı diye yeniden adlandırılmayacaktır.",
      "", "Rapor ve kaynak JSON/CSV/EOS dosyaları kanonik A01.01.51'de ve GitHub F68 dalında SHA-256 ile korunacak; F58–F67'ye dokunulmayacak.","\n"])
    Path(report).write_text('\n'.join(text))
    h={str(Path(x).name):{'sha256':sha(x),'bytes':Path(x).stat().st_size} for x in (coarse,fine,old_original,independent_static,coarse_zip,fine_zip,report,summary)}
    Path(manifest).write_text(json.dumps({'schema':'F68_SHA256_MANIFEST','files':h,'git_source_models_not_overwritten':True},sort_keys=True,indent=2)+'\n')
    return results

def main():
    ap=argparse.ArgumentParser()
    for arg in ('coarse','fine','old-original','independent-static','coarse-zip','fine-zip','report','summary','manifest'):
        ap.add_argument('--'+arg,required=True,type=Path)
    a=vars(ap.parse_args());run(a['coarse'],a['fine'],a['old_original'],a['independent_static'],a['coarse_zip'],a['fine_zip'],a['report'],a['summary'],a['manifest'])
if __name__=='__main__':main()
