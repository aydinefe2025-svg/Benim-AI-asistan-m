# J0740 F43 — 18 Kasım 2026 — Kaynak-kilitli yedi yeni nedensel EOS adayı için bağımsız statik TOV testi

**Durum:** 7/7 farklı, F42'de oluşturulmuş *yeni* nedensel barotrop için gerçek statik genel görelilik TOV çözümü ve her birinde 2.073 M☉ artan-kütle dal kökü hesaplandı. Bu, yayımlanmış yedi özgün nükleer EOS'u veya dinamik olarak kararlı yedi yeni model ailesini doğrulamaz. Son EOS Bayes hesabı **NOT_RUN**.

## Kaynak ve yöntem

- F42 orijinal yedi adayın gerçek GitHub Actions [#44269651535](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44269651535) ZIP'i SHA-256 `c8d8cdc9804a702860ab1af65b60fa25dfac0f74fce9ec6347c4271ea3353115`; ZIP CRC PASS; yedi bireysel EOS `.rns` tablosu hashleri F42 sonucu ile doğrulandı.
- 200 düğümlü RNS gösterimi, doğrudan TOV'nin RNS dönme hesabı DEĞİL. Basınç-enerji intervaline ayrık fizik temsilinde her aralıkta enerji E(P) doğrusal kabulüyle birinci-yasa entalpisi *analitik* yeniden entegre edildi. Bağımsız E(h) ve P(h) PCHIP enterpolasyonunun yapay süper-nedensellik üretebileceği görülüp kullanılmadı; akustik hız 0<cs²<=0.99 denetlendi. Kaynak modeller değiştirilmedi.
- Metrik TOV denklemleri Schwarzschild küresel geometri, entalpi koordinatı ve IVP yöntemiyle çözülerek yüzey h=0 olayı bulundu. RK45 (rtol=3e-7) ve DOP853 (rtol=1e-8) bağımsız entegratör karşılaştırıldı. Kütleye kök brentq, örneklem içi tepeye bounded optimize yalnız bracket varsa kullanıldı.
- TOV merkez yoğunluğunda 26 log-yerleştirilmiş düğüm ve tek kök çözümü; global kararlılık veya tam kritik merkezi yoğunluk yakınsaması değildir.

| F42 yeni adayın kaynak etiketi | 2.073 M☉ statik R (km) | M_TOV (M☉; yalnız lokal/örnekli) | Örneklenen en yüksek kütle (M☉) | RK45 - DOP853 ΔR (m) | Kaynak E değişimi % |
|---|---:|---:|---:|---:|---:|
| APR4_EPP | 10.697826 | 2.160272 | 2.160077 | -0.0588 | 0.169 |
| ENG | 11.400972 | 2.233431 | 2.233289 | +0.0097 | 1.037 |
| MPA1 | 12.393963 | NOT_BRACKETED | 2.462615 | -0.0288 | 0.032 |
| MS1 | 14.764266 | 2.771498 | 2.771370 | +0.0233 | 0.032 |
| MS1B | 14.619880 | 2.780058 | 2.780013 | +0.0048 | 0.032 |
| WFF1 | 9.897685 | 2.114318 | 2.114209 | +0.0198 | 20.356 |
| WFF2 | 10.557400 | 2.173988 | 2.173032 | -0.0039 | 19.972 |

## Sayısal kabul ve sınırlar

- **12/12 F43 unit/regresyon test PASS**, F42 artefakt SHA yanlışında fail-closed, sıra/kaynak nodu / acausal örnek başarısız test, entalpi terslemesi, fiziksel düşük-P yüzeyi, 7×2.073 statik kök ve RK45/DOP853 çapraz sınırı.
- Her EOS için hedef kök |M−2.073|<1e-6 M☉; RK45–DOP853 aynı merkezi yoğunluktaki yarıçap farkı <0.06 m, fakat kütle farkı 1e-5–4e-5 M☉ ve *tabloların çözünürlük duyarlılığı* onlarca metreye varabilir. Sıkı kesinlik/kararlılık sertifikası değildir.
- MPA1 için tüm incelenen aralıkta gerçek maksimum kütle dönüm noktası **çevrelenemedi**. Üst sınırmış gibi tepe sayısı verilmez.
- Gözlemsel kaynak F38 önsel-düzeltilmiş likelihood, bireysel spin ≈346.536369Hz **R_eq(M,f)**, tidal Love, 3D yoğunluk/kararlı dal, n0 kalibrasyonu ve tam 7EOS Bayes: **NOT_RUN/NOT_ESTABLISHED**.
- WFF1/2 kaynak-E enerji liftleri ~%20: aynı nükleer madde EOS'u sayılmaz. Öncelik: bu yeni adayların fiziksel kabuk/yüksek-yoğunluk modellerini meşru önsellerle denetle, ardından C/GR dönen yıldız ve ortak EOS model Bayes hesabına geç.
