# PSR J0740+6620 — 7 ÖZGÜN EOS / tam radyo kütle önseli karşılaştırması

**19 Kasım 2026 — A01.01.51.** Bu hesap F42/F49/F51'deki *yeniden inşa edilmiş yapay* EOS'ları değil, JESTER/LALSuite'in **kaynağı sabitlenmiş yedi özgün EOS modelinin statik yıldız dallarını** kullandı. Kullanıcının Windows'ta halihazırda incelenmiş 12,88 GB Salmi veri arşivi **yeniden indirilmedi, açılmadı veya yeniden test edilmedi**.

## Bu hesapta fiilen elde edilen sonuç

1. JESTER kaynak commit `e6768650ce992abfd1153a6833857572fe5cd230` içindeki 7 özgün `APR4_EPP`, `ENG`, `MPA1`, `MS1`, `MS1B`, `WFF1`, `WFF2` NPZ dosyası GitHub Actions'da çekildi, her biri F65 kaynak SHA-256 ile doğrulandı. Tam yedi dosyayı ve hash manifestini içeren orijinal GitHub artifact ZIP SHA-256: `2521501b7aaf0afec0e067d7bbb680ae1c36327a1f64c83070b58d4e2bc5e119`.
2. Daha önce hesaplanan **gerçek 1.137.394 ağırlıklı Salmi gözlem örneğinin** altı `q(M,R)/pi_eff(M,R)` KDE alanını içeren F38 ZIP **bayt-bayt yeniden doğrulandı**, SHA-256: `4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307`. Gözlem örnekleri, photon dosyaları ve orijinal kaynak 12,9 GB arşiv yeniden işlenmedi.
3. Yedi özgün JESTER/LALSuite statik kütle–yarıçap dizisi alındı. Kütlenin düşük-kütle sınırındaki çok-değerli tablolardan yalnız **M ≥ 1 M☉ tek-değerli yüksek-kütle dalı** seçildi. Fiziksel EOS veya hidrodinamik yıldız kesilmiş sayılmadı: statik bir yıldız ancak yayınlanmış kaynak `M_TOV` değerine dek mevcut sayıldı.
4. **Tüm radyo kütle önseli ±5σ** (`M~TruncNormal(2.082,0.0703 M☉)`) üzerinde gerçek çoklu nümerik integral hesaplandı. Bu, F49/F51'in yalnız bir *ortak kütle penceresi* içindeki koşullu skorlarının yerine geçmez; **özgün yedi EOS ve tam destekli *ayrı* statik tanı hesabıdır**. Radyo önseli ikinci kez çarpılmadı; gözlem pozisyonunda kaynak-prior destek maskesi uygulanarak NICER+XMM fazladan bağımsız çalışma gibi çift sayılmadı.

Kullanılan matematiksel ölçü (belirtilen model altında):

`I_i = ∫_{Mlo}^{min(Mhi,M_TOV,i)} π_radio(M) × L_F38,approx(M,R_i,static(M)) / Z_source dM`.

`L_F38,approx/Z_source = KDE[p_source(M,R|D)] / π_source(M,R)`; **gerçek yeni X-PSI pulse-profile photon likelihood hesaplaması değildir**. Eşit yedi *ayrık* model önseli kabul edilirse, hesaplanan koşullu ağırlık `w_i=I_i/Σ_j I_j` olur. Bu seçilmiş statik model kümesi tanı hesabının nihai matematiksel sonucudur, genel nükleer madde posterioru değildir.

## Tam kütle önseli için yedi özgün kaynak modeli

| EOS (özgün LALSuite) | Statik M_TOV (M☉) | Statik R, M=2,073 M☉ (km) | Medyan I_i (L/Z) | Eşit 7-model önseline göre koşullu ağırlık | Altı KDE'nin ağırlık aralığı | Statik M_TOV üzerinde kalan radyo önseli |
|---|---:|---:|---:|---:|---:|---:|
| **MPA1** | 2,468639 | 12,451532 | **2,41407** | **%40,47** | %38,09–42,18 | ~%0,00 |
| **ENG** | 2,252090 | 11,504800 | **1,71721** | **%28,79** | %27,34–29,88 | %0,78 |
| APR4_EPP | 2,159167 | 10,698632 | 0,52502 | %8,80 | %7,79–9,92 | %13,62 |
| MS1B | 2,797101 | 14,777978 | 0,48157 | %8,07 | %7,98–8,36 | ~%0,00 |
| MS1 | 2,799082 | 15,011622 | 0,38932 | %6,53 | %6,38–6,85 | ~%0,00 |
| WFF2 | 2,185070 | 10,575394 | 0,38697 | %6,49 | %5,37–7,85 | %7,13 |
| WFF1 | 2,113670 | 9,929483 | 0,05129 | %0,86 | %0,43–1,62 | %32,62 |

Altı ayrı yüzeyin hepsinde bu **statik** seçimde MPA1 > ENG sonucu çıktı. Altı yüzey **aynı foton gözleminin farklı KDE / kaynak ağırlık işlemleridir**, birbirinden bağımsız astronomik gözlem değildir; bunlar ortalamalanarak örneklem büyüklüğü altı kat yapılmadı.

## Dönme ve sistematik duyarlılığı (ayrı fiziksel etiketlerle)

Özgün MPA1 için F62/F63 kaynak-native tam GR RNS yıldızı, M≈2,073 M☉, f≈346,61 Hz, `R_eq=12,53329593 km`; aynı kaynak statik MPA1 değeri `R≈12,45153 km`. Yani tek kaynak modelinde **+81,76 metre gerçek dönme farkı** önceden hesaplanmıştır. Bu, kalan altı EOS'un dönme düzeltmesine birebir taşınamaz.

**Yalnız duyarlılık senaryosu (yeni RNS yıldızları değildir):** yedi statik yarıçap eğrisinin tamamı varsayımsal aynı +0,082 km kaydırıldığında MPA1 koşullu medyan ağırlığı %38,36, ENG %29,69 olur. Tüm yarıçaplar +0,30 km varsayımsal kaydırıldığında MPA1 ~%32,47, ENG ~%30,94. +0,40 km kaydırılınca sıralama **ENG lehine döner**. Bu, gerçek fiziksel spin düzeltmesi olmadığı gibi gözlemsel belirsizlik aralığı da değildir; gerçek 7 EOS dönme eğrileri olmadan statik sonucun fiziksel model sıralaması diye sunulamayacağını ölçer.

## Kabul ölçütleri ve eksiksiz tekrar üretim

- **9/9 yerel test PASS:** kaynak dosyalarının orijinal SHA eşleşmeleri; 7 ayrı kaynak EOS yüklemesi; radyo önselinin 1'e integrali; X-PSI geometri dışı destek sıfırlama; sabit-likelihood tam aralıkta 1 elde edilmesi; M_TOV sonrası yıldız olmayan bölgenin sıfır sayılması; altı gerçek F38 KDE kaynağı; 6×7 tam integralin yedi koşullu ağırlık toplamının 1 olması ve örneklenmiş 1.001/2.001/4.001/8.001 düğüm integrasyon yakınsaması; değiştirilmiş NPZ kaynağının reddedilmesi.
- Çıktılar `J0740_original_seven_static_full_mass_KDE_integrals_20261119.json`, `J0740_original_seven_static_full_mass_results_20261119.csv`, `J0740_original_seven_static_radius_sensitivity_20261119.json`; tekrar çalışan kod `original_seven_fullmass_integral.py`, test `test_original_seven_fullmass.py`, duyarlılık kodu `rotating_radius_systematic_sensitivity.py`.
- Eksik kod/surface/NPZ uydurulmadı. Kaynak 2D yüzeyleri ve yedi özgün EOS arşivleri **kanıt ZIP'inde birlikte** bulunduğundan hesap offline tekrar çalıştırılabilir. Başka kamuya açık sürümün aynı sayısal sonucu vereceği garanti edilmez.

## Açık fiziksel kapsam

Bu deney **matematiksel olarak tamamlanmış özgün-yedi-EOS tam-kütle *statik model* karşılaştırmasıdır**. PSR J0740+6620 gerçekten 346,536369 Hz döndüğünden, fiziksel kabulü nihai saymak için yedi kaynak EOS'un tamamında *kaynağa uygun* gerçek RNS dönen R_eq(M,f) dizisi gerekir. Ayrıca önceki F66'da altı kaynak EOS için LALSuite düşük-P spline negatif ses hızı; F61'de ENG/WFF1/WFF2 merkezinde ışıküstü ses hızı saptanmıştı. Bunlar özgün EOS adını koruyarak sessizce düzeltilemez; fiziksel kabulü etkiler. Salmi'nin run1 X-PSI v1.2.0 günlüğü ile makale v1.2.1 beyanı arasındaki resume sürümü ayrımı da tam photon-level yeniden yürütmede belgelenmelidir.

**Hemen uygulanabilir son aşama:** Yedi özgün kaynak EOS'ta tüm kütle dalı için 346,536369 Hz tam GR yıldız dizileri, sayısal yakınsama ve fiziksel kabuk/çekirdek kabulü; ardından mevcut tanımlı kaynak-prior düzeltilmiş gözlem integraliyle nihai EOS modeli seçimi. Aynı 12,9 GB veri arşivini yeniden indirme/açma bu aşamanın gereği değildir.

## Bağımsız 42/42 toplama tanığı

Tam F38 2D KDE ZIP dosyasından türetilen **kaynak-kilitli 6 yüzey × 7 EOS × 401 örnekli 1D olabilirlik izi** `J0740_original_source_F38_line_witness_20261119.json` içinde kaydedildi. Bu tanık, bütün 2D kaynakların yerine geçmez; tam F38 ZIP yukarıdaki kanıt paketinde korunmaktadır. Ayrı `verify_native_source_massline_witness.py` doğrulayıcısı, yedi NPZ kaynak hash'ini yeniden kontrol ederek özgün kaynak kütle–yarıçap eğrilerini ayrı kurdu, kaynak destek maskesini ve tüm 42 kütle integralini yeniden hesapladı: **42/42 PASS**, tam 2D yüzeyli 4001 düğüm referansına göre **en yüksek bağıl integral farkı 7,321×10⁻⁶**. Bu yalnız sayısal yeniden hesap uyumudur, foton modelinin doğrulanması değildir.
