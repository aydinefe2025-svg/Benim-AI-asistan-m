# A01.01.51 — F61: 7 özgün EOS ile 24 doğrudan LALSuite statik yıldız çözümü

**18 Kasım 2026 | yeni gerçek sayısal fizik, kaynak-doğrulanmış; nihai EOS Bayes sonucu değil.**

## Gerçekte çalıştırılan deney

Aynı kaynak commit `e6768650ce992abfd1153a6833857572fe5cd230` içinde byte-hash kilitli **7 özgün JESTER/LALSuite EOS** kullanıldı. F42'nin enerji düzeltmesi, soğuk-gaz üstü kaplaması veya F49/F51'in değiştirilmiş EOS tabloları **kullanılmadı**. Sabit doğrudan LALSuite **7.26.4** Python dağıtımının `SimNeutronStarTOVODEIntegrate(Pc, native_EOS)` çağrısıyla merkez basıncı çözüldü; M=2.073, 2.175, 2.200, 2.225, 2.250 M☉ hedeflerinde gerçekten çözüm elde edilen 24 yıldız kaydedildi. Elde edilen yarıçaplar kaynak JESTER NPZ'deki 500 noktalı statik TOV eğrisiyle **karşılaştırıldı**. Aynı temel fizik çözücüsünden türetilmiş iki ürün oldukları için bu, tamamen bağımsız ikinci fizik algoritması kanıtı **değildir**.

**Kabul:** 7/7 özgün modelde 2.073 M☉ kaynak-matched gerçek statik kök; tüm 24 kökte M artığı <2×10⁻⁷ M☉ ve kaynak R referansı farkı <0,000172 km; başlangıç 10/10 matematik/etiket birim testi; [CI #44376272168](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44376272168) PASS. CI içeriğinin SHA manifesti ve ZIP CRC ayrıca doğrulandı.

## M = 2.073 M☉ özgün EOS sonuçları

| Kaynak EOS | Doğrudan statik R (km) | Merkez cₛ²/c² | Özgün kaynağın statik M_TOV üstü (M☉) | Örneklenen yoğun çekirdek nedenselliği |
| --- | ---: | ---: | ---: | --- |
| APR4_EPP | 10.698664 | 0.88188 | 2.15917 | GEÇTİ — yalnız örnekleme |
| ENG | 11.504802 | 1.06324 | 2.25209 | KALDI |
| MPA1 | 12.451545 | 0.72460 | 2.46864 | GEÇTİ — yalnız örnekleme |
| MS1 | 15.011630 | 0.53209 | 2.79908 | GEÇTİ — yalnız örnekleme |
| MS1B | 14.777992 | 0.54300 | 2.79710 | GEÇTİ — yalnız örnekleme |
| WFF1 | 9.929517 | 1.15844 | 2.11367 | KALDI |
| WFF2 | 10.575413 | 1.11442 | 2.18507 | KALDI |

**Önemli fiziksel ayrım:** ENG/WFF1/WFF2 merkezinde doğrudan LALSuite analitik türevinden `cₛ²/c²>1` çıkıyor; söz konusu yıldız modellerinde özgün tablonun fiziksel nedensellik şartı başarısızdır. ENG merkezindeki değer daha yüksek kütlede tekrar 1'in altına düşse bile yıldızın ara katmanlarındaki >1 örnekler kaybolmuyor. MPA1/MS1/MS1B yüksek yoğunluklu çekirdekte örneklenmiş nedensellikten geçiyor, ancak özgün tablolarının düşük basınç tarafındaki negatif türev düğümleri nedeniyle **bütün yıldız fiziksel kabulü geçmedi**. APR4_EPP 2.073 M☉ için örneklenmiş yıldız içi kontrolden geçiyor; daha yüksek basınçta kaynak EOS acausality var. Hiçbir özgün EOS bu rapordan bir **sürekli küresel fiziksel sertifika** elde etmiyor.

## Daha önce bilinmeyen yüksek-kütle fiziksel ayrımı: gerçek statik dallar

| Özgün EOS | M=2.175 statik çözüm | M=2.250 statik çözüm | Kaynak statik M_TOV (M☉) | Radyo önselinin statik M≤M_TOV kısmı |
| --- | --- | --- | ---: | ---: |
| APR4_EPP | YOK (statik) | YOK (statik) | 2.159167 | 86.38282% |
| ENG | VAR | VAR | 2.252090 | 99.22291% |
| MPA1 | VAR | VAR | 2.468639 | 100.00000% |
| MS1 | VAR | VAR | 2.799082 | 100.00000% |
| MS1B | VAR | VAR | 2.797101 | 100.00000% |
| WFF1 | YOK (statik) | YOK (statik) | 2.113670 | 67.38260% |
| WFF2 | VAR | YOK (statik) | 2.185070 | 92.86964% |

Burada **M_TOV kaynak statik eğrisinden** alınmıştır, yeni frekans-346.536369 Hz maksimumu değildir. Statik yıldız M_TOV üzerinde yoksa bu, gözlenen hızda dönen yıldızın da yok olduğunu **kanıtlamaz**. Bu nedenle henüz hiçbir modele radyo önselinin eksik bölgesini zorla sıfır saymadım. Statik R yerine R_eq(M, spin) konursa ayrı **gerçek kaynak-EOS RNS** koşusu ve sabit-J kararlılık denetimi gerekir. Statik % göstergeleri gözlemsel Bayes ağırlığı değildir.

## Kaynak ve sınır kanıtları

- Özgün NPZ dosyalarının 7 SHA-256'sı [pinned EOS fixture](../rotating_gr/fixtures/pinned_eos_center_fixture.json) ile karşılaştırıldı; doğru dosya dışında işleme izin verilmedi.
- Merkez `cₛ²/c²` LALSuite'in **yerel analitik türevinden** doğrudan alındı; kaynak düğümlerinin 2.8×10¹⁴ g/cm³ üstü ve altı ayrı tarandı. Düğüm aralarında başka ihlal bulunmadığını **kanıtlamaz**.
- `F61_original_seven_LAL_static_TOV.json` tüm 24 çözüm için merkez basınçları, kaynak karşılaştırma farkları, kök braketleri, fiziksel taramalar, yıldız bulunmayan hedefler ve kaynak hash'lerini içeriyor.
- **Henüz yapılmayan:** 7 özgün EOS için tam 346.536369 Hz GR RNS çözüm eğrisi; tüm aralık boyunca global (özellikle sabit-J) kararlılık; özgün X-PSI nuisance marjinalizasyonu ve kaynak `π_eff(M,R)`; gerçek kaynak fotonlarıyla yedi-EOS Bayes hesabı. Photon/NICER arşivi yeniden indirilmedi, aynı fotonlar iki kez sayılmadı.

**Bundan sonraki fizik kapısı:** MPA1 için kaynak-hash kilitli 346.536369 Hz RNS gerçek çözümlerini M=2.175–2.25'te elde etmek ve orijinal tablodaki alt-basınç sorununun *fiziksel etkisini* ayrı sınıflandırmak. ENG'nin çekirdekteki acausal değerleri gizlenmemeli. Kesin fiziksel EOS Bayes çıkarımı yapılmadan yedi modelden birine zafer ilan edilmemeli.