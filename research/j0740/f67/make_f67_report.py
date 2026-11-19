import hashlib,json,zipfile,pathlib,datetime
D=pathlib.Path('/mnt/data/f67')
E=D/'final_ci'
F=E/'F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json'
T=E/'F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat'
Z=pathlib.Path('/mnt/data/F67_verified_alternate_MPA1_PCHIP_TOV_and_cs2_extrema_20261119.zip')
J=json.loads(F.read_text())
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
with zipfile.ZipFile(Z) as z:
 assert z.testzip() is None
 assert {a.filename for a in z.infolist()} >= {F.name,T.name,'F67_SHA256_receipt_20261119.json'}
R=J['new_M2p073_PCHIP_root']; U=J['independent_u_v_at_same_root'];Q=J['analytic_piecewise_cubic_sound_speed_extrema']
assert J['not_original_MPA1'] and J['rotating_RNS_equilibria_on_alternative']=='NOT_RUN'
assert J['seven_original_EOS_Bayes']=='NOT_RUN'
assert Q['all_piecewise_interval_extrema_checked'] and Q['new_alternate_mathematical_interpolant_causal_to_star_center']
assert R['M_msun']>2.072999 and R['M_msun']<2.073001
assert abs(R['R_km']-U['R_km'])<.00001
assert sha(T)==J['alternate_firstlaw_table_sha256']
DELTA_M=(U['M_msun']-R['M_msun'])
DELTA_R=(U['R_km']-R['R_km'])*1000
STATIC_DIFF_M=(R['R_km']-J['original_LAL_F61_2p073_static_R_km'])*1000
P=pathlib.Path('/mnt/data/f67/F67_science_report_20261119.md')
report=f'''# A01.01.51 — F67: MPA1_PCHIP_COLD_V1 yeni EOS temsili, soğuk birinci yasa ve iki bağımsız statik GR yıldızı

**Tarih: 19 Kasım 2026. Yeni deney, F58–F66 tekrarı değil.** Bu model, nükleer **özgün MPA1 değildir**; F42/F51 iyileştirmeleri veya özgün nükleer EOS etiketi altında sunulamaz. Model adı: `{J['model_label']}`.

## Doğrudan fiziki giriş kaynağı

- LALSuite **7.26.4** kurulu paketinden alınan özgün MPA1 **102-satırlık basınç–enerji** tablosu; ham kaynak SHA-256 `{J['installed_original_MPA1_raw_source_sha256']}` (F66 orijinal kaynak tablosuyla birebir).
- JESTER özgün MPA1 NPZ referansı `{J['original_JESTER_MPA1_npz_sha256']}`. Bu kaynağın 836 düğümlü **spline türevi** nükleer EOS tablosu ile aynı fiziksel temsil olduğu iddia edilmedi.
- Ham kaynak P,epsilon düğümleri değişmeden logP→logepsilon **PCHIP** biçiminde yeniden temsil edildi. F66'nın log-log kübik negatif-türev sorunu bu yeni hipotezde ayrı değerlendirildi; özgün LALSuite dosyaları, eski F58–F66 raporları değiştirilmedi.
- Geometrik birimler: P ve epsilon m⁻², yıldız R km, M Güneş kütlesi. Soğuk barotropik birinci yasa: `H(P)=∫dP/(epsilon+P)` ve `n(P)/n0=(epsilon+P)/(epsilon0+P0)·exp[-H(P)]`; başlangıç `n0=1` **keyfi normalizasyon**, µ0 ve fiziksel baryonik M0 **ölçümü değildir**.

## Yeni bağımsız statik TOV sonucu

İstenen hedef kütle **2,073 M☉**, özgün F61 LALSuite statik TOV yarıçapı **{J['original_LAL_F61_2p073_static_R_km']:.9f} km**. Ayrı alternatif modelle doğrudan entalpi koordinatlı genel görelilik TOV denklemleri çözülerek **M={R['M_msun']:.9f} M☉, R={R['R_km']:.9f} km**, merkez geometrik basınç **{R['central_pressure_geom']:.12e} m⁻²** bulundu.

Yeni matematiksel EOS temsilinin tahmini statik yarıçapı, özgün MPA1 F61 statik yıldızından **{STATIC_DIFF_M:+.6f} metre** farklıdır (yaklaşık **{abs(STATIC_DIFF_M):.2f} metre daha küçük**). Bu, gözlemsel bir yarıçap değişim ölçümü veya hata çubuğu değildir; **iki farklı sayısal EOS hipotezinin model duyarlılığıdır**.

İkinci bağımsız `(u=r², v=m/r)` TOV formülasyonu *aynı merkez basıncında* M={U['M_msun']:.9f} M☉, R={U['R_km']:.9f} km üretti. İki çözüm arasında |ΔM|={abs(DELTA_M):.9g} M☉ ve |ΔR|={abs(DELTA_R):.6f} metre, bağıl M farkı {J['numerical_comparison']['mass_relative']:.4e}. Entegrasyon iç ızgara/kuadratürünün 12×32 ve 24×48 noktaları arasında aynı merkez basıncında ΔR={J['numerical_comparison']['coarse_fine_R_at_same_pc_km']*1000:.6f} metre; bu, bütün fizik model hatasının sınırı değildir. Yıldız yüzeyi çözümü EOS ham tablosunun en alt pozitif basıncında sonlandırıldı; gerçek P=0 yüzeyine ilişkin ek fizik sınırı vardır.

## Ses hızının bütün PCHIP kübik parçaları üzerinde ekstremum taraması

- Yeni EOS'ta yıldız merkez basıncına kadar **{Q['piecewise_cubic_raw_intervals']} parçalı kübik aralık** işlendi. `c_s²/c² = exp(x-s(x))/s'(x)` [x=lnP, s=lnε]; türevin kritik noktaları `(1-s')s' - s''=0` dördüncü derece polinomundan bulunup sınırlarla birlikte sınandı: **{Q['quadratic_times_quadratic_quartic_real_stationary_roots']} iç gerçek kritik nokta**.
- PCHIP modeli içinde hesaplanan min–maks **{Q['floating_polynomial_extrema_cs2_min']:.12g} – {Q['floating_polynomial_extrema_cs2_max']:.12g}**; incelenen model yıldızında negatif ya da ışıküstü `c_s²` yok. Ayrı 1.785 örnekli yoğun tarama da aynı sonuçla uyuştu.
- Bu, **yeniden oluşturulmuş sayısal PCHIP temsilinde kayan noktalı polinom köklerine dayalı kapsamlı ekstremum denetimidir**; nükleer madde geçişi, mikrofizik bileşim, faz kararlılığı, orijinal LALSuite EOS'un sürekli nedenselliği veya belirsizlik içeren fiziksel sertifika **değildir**.

## Testler, kaynak bütünlüğü ve kanıt

- GitHub PR **#631**, yeni ayrı F67 kodu, iki bağımsız statik GR TOV integratörü; **18/18 fail-closed yerel ve GitHub test**, son kod CI **3/3**. Ana gerçek CI `https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44481616029`.
- Orijinal kaynak SHA-256 yukarıda; sonuç JSON SHA-256 `{sha(F)}` ({F.stat().st_size} bayt); alternatif termodinamik tablo SHA-256 `{sha(T)}` ({T.stat().st_size} bayt); GitHub CI ZIP SHA-256 `{sha(Z)}` ({Z.stat().st_size} bayt), ZIP CRC **PASS**. İç manifestte sonuç ve tablo hashleri eşleşti.
- Baryon µ0 bağımsız olarak kalibre edilmedi; X-PSI'nin **orijinal foton ve nuisance likelihood** testi yapılmadı, **346,536369 Hz dönen RNS yıldızı bu ALTERNATİF modelle çalıştırılmadı**; yedi özgün EOS fiziksel kabulü ve tam, mükerrer-önselsiz Bayes sonucu **NOT_RUN**.
- Özgün F58–F66 verilerinin üzerine yazılmadı; **F67 ayrı** kaydedildi. Bu sonuçlar bilimsel denetim ve yeni araştırmalar için geçerli matematiksel model duyarlılık bulgusudur, nihai nükleer EOS keşfi değildir.

## Sıradaki gerekli fizik kapısı

F67 alternatif soğuk EOS'un gerçek düşük-P kabukla µ0/entropi faz sınırı, RNS doğrudan 346,536369 Hz yüksek çözünürlük ve kararlılık çözümü; ardından özgün NICER/XMM foton likelihood için bütün nuisance marjinalizasyonu ve çift sayımı engellenmiş yedi fiziksel EOS Bayes. Hesaplanmayan adımlar kapatıldı diye işaretlenmez.
'''
P.write_text(report)
summary={
 'schema':'F67_J0740_SEPARATE_MPA1_PCHIP_COLD_FIRSTLAW_STATIC_TOV_20261119',
 'model':J['model_label'],'original_EOS_modified':False,'raw_original_mpa1_sha256':J['installed_original_MPA1_raw_source_sha256'],
 'source_raw_rows':102,'target_mass_msun':2.073,
 'original_F61_static_radius_km':J['original_LAL_F61_2p073_static_R_km'],
 'new_F67_alternative_static_radius_km':R['R_km'],
 'new_minus_original_static_radius_m':STATIC_DIFF_M,
 'independent_TOV_u_v_minus_rm_radius_m':DELTA_R,
 'independent_TOV_u_v_minus_rm_mass_msun':DELTA_M,
 'cold_mu_over_mu0_firstlaw_max_relative_error':J['n_from_exact_cold_chemical_identity_max_relative'],
 'piecewise_cubic_extrema':Q,
 'new_alternate_nuclear_model_physically_certified':False,
 'rotating_alternate_RNS':'NOT_RUN', 'native_photon_XPSI':'NOT_RUN', 'seven_original_EOS_bayesian_comparison':'NOT_RUN',
 'native_ci_run':44481616029, 'native_ci_checks':'3/3 green','unit_tests':'18/18',
 'hashes':{'result_json_sha256':sha(F),'thermo_table_sha256':sha(T),'CI_ZIP_sha256':sha(Z)},
 'ci_zip_crc_ok':True,
 'notes':'F67 is not original nuclear MPA1. It is an alternative PCHIP interpolation and cold first-law relative n; mu0 unknown.'
}
(D/'F67_science_summary_20261119.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
manifest={'schema':'F67_J0740_SHA256_SOURCE_AND_EVIDENCE_ACCEPTANCE_20261119','files':{str(f.name):{'sha256':sha(f),'bytes':f.stat().st_size} for f in [F,T,Z,P,D/'F67_science_summary_20261119.json',D/'f67_mpa1_pchip_firstlaw_tov.py',D/'test_f67_mpa1_pchip_firstlaw_tov.py',D/'j0740-f67-mpa1-alternate-cold-tov.yml']},'original_MPA1_source_raw_sha256':J['installed_original_MPA1_raw_source_sha256'],'target_GitHub_CI_commit':'68da20cfee6ae7141df880eeb420cf7fc20fdfc3','zip_crc_pass':True,'not_native_photon_eos_bayes':True}
(D/'F67_SHA256_acceptance_manifest_20261119.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
print('science report',P.stat().st_size,sha(P))
print('summary',summary)
print('receipt SHA',sha(D/'F67_SHA256_acceptance_manifest_20261119.json'))
