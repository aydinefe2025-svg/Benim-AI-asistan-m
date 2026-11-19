# F75 | PSR J0740+6620 yedi özgün EOS — kaynak kökenli 2,073 M☉ nedensellik ayrıştırması

**Tarih:** 19 Kasım 2026  
**Kapsam:** Özgün Salmi F38 KDE/RNS sıralamasına fiziksel kabul denetimi. Bu, önceki yedi-model hesaplamasını tekrar etmez.

## Doğrulanmış bağımsız veri işlemi

- Kaynak: kanonik `/A01.01.51/PSR_J0740+6620/original_spin_recovery/J0740_ORIGINAL_7_ROTATING_GR_WFF_RESCUE_F38_FULL_EVIDENCE_20261119.zip`, SHA-256 `0306d0ed4b15f25c4831433aecb5f536cefd803082402a31c6461ea6750559bb`.
- Paket içindeki yedi özgün `JESTER@e6768650ce992abfd1153a6833857572fe5cd230` LALSimulation EOS `.npz` SHA'ları ve 323 kaynak RNS C yıldızının yedi orijinal GitHub artifact JSON/ZIP SHA'ları **ayrı ayrı kontrol edildi**. Kaynak yıldız çözümü, KDE ve büyük foton TAR'ı yeniden çalıştırılmadı.
- Kaynakta basınç `p`, enerji yoğunluğu `e` ve `cs2=c_s²/c²` dizileri; LAL geometrik enerji yoğunluğu `e [m⁻²]` → `(c²/G)/1000` ile `g/cm³` dönüşümü; özgün RNS C yıldızlarının `central_energy_density_g_cm3` merkez yoğunlukları karşılaştırıldı.
- 2,073 M☉ merkez yoğunluğu **yalnız özgün kaynak yıldızların birinci kütle-artan kolundaki iki komşu gerçek çözüm arasında doğrusal interpolasyonla** hesaplandı. Bu interpolasyon yeni bir GR çözümü değildir. Kaynakta gözlenmeyen kütle veya yıldızlar oluşturulmadı.
- Denetim noktaları: her kaynak dizi düğümünde `0 ≤ c_s²/c² ≤ 1`, `Δe>0`, `Δp>0`. Bu kriterler **örneklenmiş düğüm denetimi**; aradaki süreklilik, özgün mikrofizik, ilk yasa, fiziksel kabuk eşleştirmesi ve global sabit-J kararlılığı hakkında sertifika değildir.

## Kaynaktan türetilmiş ölçüm tablosu

| Özgün EOS | 2,073 M☉ merkezi (10¹⁵ g/cm³) | Tüm EOS negatif cs² düğümleri | Tüm EOS ışıküstü düğümler | Referans yıldız içindeki negatif | Referans yıldız içindeki ışıküstü | Kaynak düğüm kapısı |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| APR4_EPP | 1.753976 | 0 | 2 | 0 | 0 | PASS_KNOTS_ONLY |
| ENG | 1.482763 | 1 | 58 | 1 | 1 | FAIL_OR_UNRESOLVED |
| MPA1 | 1.015566 | 1 | 0 | 1 | 0 | FAIL_OR_UNRESOLVED |
| MS1 | 0.614448 | 1 | 0 | 1 | 0 | FAIL_OR_UNRESOLVED |
| MS1B | 0.616286 | 1 | 0 | 1 | 0 | FAIL_OR_UNRESOLVED |
| WFF1 | 2.086912 | 1 | 69 | 1 | 17 | FAIL_OR_UNRESOLVED |
| WFF2 | 1.761252 | 1 | 78 | 1 | 8 | FAIL_OR_UNRESOLVED |

**Önemli fiziksel yorum:** APR4_EPP referans kütlede örneklenmiş EOS düğümlerini geçer, fakat EOS'un *tüm yüksek yoğunluk aralığında* 2 ışıküstü düğümü vardır; APR4'ün global fiziksel kabulü de tamamlanmış değildir. ENG/WFF1/WFF2 özgün kaynak örneklerinde referans kütlenin merkezine kadar ışıküstü ses hızı bulunur. MPA1/MS1/MS1B ve ENG/WFF1/WFF2 için ortak düşük-basınç kaynak enterpolasyonunda bir negatif `cs2` düğümü ve bir `e` tersine dönen kaynak kenarı vardır; bu, özgün ham nükleer tablonun mutlaka fiziksel olarak ters olduğu anlamına gelmez. F65/F66 özgün ham tablo ↔ LALSuite enterpolasyon ayrımını önceden göstermişti. Hiçbir model üzerinde fiziksel özellikleri gizlemek için örtük düzeltme yapılmadı.

## Bilimsel karar ve kaynak-foton kapısı

1. 19 Kasım'da PR #679 ile matematiksel olarak elde edilen **MPA1 > ENG > APR4_EPP** sırası yalnızca *özgün yedi sayısal model ve altı F38 KDE* çerçevesinde dayanıklıdır. Buradaki yeni F75 bulguları, sırayı fiziksel EOS kararı olarak yükseltmeyi **engeller**. Sıralama teoremi yanlışlanmış değildir; varsayımları fiziksel sertifika değildir.
2. MPA1'in en yüksek model puanı ile seçilen MPA1 kaynak düşük-P enterpolasyonunun fiziksel kabul problemi ayrı tutulmalı. Gerçek bir düzeltme yalnız fiziksel kabul edilen **yeni kimlikli EOS adayı** ve yeniden TOV/RNS/olabilirlik çalışmasıyla değerlendirilebilir; eski MPA1 ile özdeş sayılamaz.
3. Foton seviyesindeki Salmi 2024 X-PSI/NICER+XMM analizinde özgün olay/yanıt/atmosfer/arka plan ve nuisance önselleri ile native Poisson kaynak olabilirliği bu F75 paketinde **çalıştırılmadı**. F38 posterior/önsel oranı gözlemsel vekildir; foton düzeyinde Bayes faktörü değildir. Radyo kütle önselinin **bir kez** hesaba katılması ve kütle–eğim kovaryansı kritik olmaya devam eder.
4. Gelecek gerçek kabul kapıları: (a) özgün ham EOS ve enerjiyi/baryon yoğunluğunu ilk-yasayla tutarlı yeniden kur, tüm yıldız yoğunluk bölgesinde doğrudan ve yüksek çözünürlüklü nedenselliği kanıtla; (b) fiziksel EOS eşleştirme ve sabit-J stabilitesini gerçek RNS ile doğrula; (c) özgün foton ve nuisance konfigürasyonunu erişilebilir kaynakla yeniden çalıştır, hem kaynak verisini hem önsel ayrıştırmasını doğrula. Başarılana kadar `physical_admission=NOT_ESTABLISHED`, `XPSI_photon_likelihood=NOT_RUN`, `seven_EOS_Bayes=NOT_RUN`.

## Kabul, kanıt ve sınır

- `python -m unittest -v test_f75_original_eos_causality_gate`: **10/10 PASS**, sentetik birim testler.
- Gerçek kaynak SHA ve RNS-kökenli yedi-model üretim: **7/7 başarıyla okundu ve rapor üretildi**. Bu bir gerçek-dosya işleme kabulüdür, fizik sertifikası değil.
- Orijinal F38 sıralama bilimsel referansı: [PR #679](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/679); kurtarılan WFF sayısal kolu: [PR #670](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/670).
- Literatür yöntemleri: [Salmi et al. 2024](https://doi.org/10.3847/1538-4357/ad5f1f); [LALSuite EOS belgelemesi](https://lscsoft.docs.ligo.org/lalsuite/dev/lalsimulation/group___l_a_l_sim_neutron_star_e_o_s__c.html); [EOS kaynak-foton çıkarımı](https://journals.aps.org/prd/abstract/10.1103/z2hd-w9sy).

**Sonuç sınıfı:** `F75_SOURCE_SAMPLED_CAUSALITY_DIAGNOSTIC_COMPLETE`, *fiziksel kabullü yedi-EOS sonucu tamamlanmadı*. F75 dışında EOS sıralaması tekrar hesaplanmadı.