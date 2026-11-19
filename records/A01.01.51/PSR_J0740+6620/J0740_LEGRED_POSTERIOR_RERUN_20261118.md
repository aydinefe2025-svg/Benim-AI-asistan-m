# PSR J0740+6620 — Legred koşullu posterior yeniden üretimi (18 Kasım 2026)

## Sonuç ve yürütme kanıtı

25 Ekim 2026 tarihli koşullu Legred GP-EOS güncellemesi iki bağımsız yolla tekrar üretildi: GitHub Actions ve Windows 11/JAX CPU yerel çalıştırması. İkisi de aynı `research/j0740/historical_20261025` yöntemini uygulayıp tarihsel kayıtla tolerans içinde eşleşti. Bu, geçmişteki hesabın yeni çalıştırmayla doğrulanmasıdır; yeni bir model bağımsız fiziksel EOS posterioru değildir.

GitHub Actions run [#44321341032](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44321341032) başarılı tamamlandı (job `134860781146`; 18 Kasım 2026 14:19 UTC). Çalıştırma commit’i `45262d5d60a884c33b19b61be75e5af87a0030e8`. Artifakt SHA-256: `c774c5788897b8c1cfdc12e2c4972fc500db5872311e766648fc223065f5ec59`. İlk denemenin başarısızlığı yalnızca manifest satır sonu adımındaydı; düzeltilmiş tekrar başarılı oldu.

Yerel koşu PASS: Python 3.12.10, Windows 11, JAX CPU; 26.70 saniye. Çalıştırılan tarihsel kodun Git blob SHA-1’i `9fa9db8b95107c291688117cda6d41a470e6775e`, SHA-256’i `29e0567aa88d6ae7dd86719b01c0125ddccf82bf9937b4c72031ad4b5322899f`. Yerel adapter SHA-256 `518043db9acd74c33b09f8ebee2638a854c1e759d43642ba345e48110616f0f0`; üç değişiklik yalnızca dosya yolu uyarlamasıdır, hesaplama algoritması değiştirilmemiştir.

## Kaynak veri bütünlüğü

ATL `j0740-eos-audit/j0740/raw_bundle_parts/` altında `part-000`–`part-053`, 54/54 parça, toplam 222,910,037 bayt indirildi ve yeniden birleştirilmiş paket bütünlük kontrolünü geçti. Paket MD5 `9fec0d9cd29df816bfea78565d0a6bb2`; SHA-256 `5057752bec77b2417368fe144a6c1fc94203ce1eb15b975613a9ca334ddbfc2f`.

| Girdi | Bayt | SHA-256 |
|---|---:|---|
| Salmi `mr_samples_and_contours.tar.gz` | 40,605,003 | `1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8` |
| Miller `NICER_XMM_J0740_full_original_weighted.txt` | 168,073,694 | `125cee5208d31c25791023e84e020362df56ad3ef808e8b325f57c2be65a79e2` |
| Legred `LCEHL_EOS_posterior_samples_PSR_GW_NICER.h5` | 192,213,112 | `39ff1308fb2461eddaf82525ec8581db554c0d3907431ba7d23a04f4621b5abe` |

İçerik sayımları Salmi 379,669 eş-ağırlıklı örnek, Miller 1,600,920 özgün ağırlıklı satır ve Legred 10,000 EOS olarak doğrulandı. GitHub Actions kaynak girdilerinin MD5, boyut ve SHA-256 değerleriyle yerel doğrulama eşleşti.

## Yeniden üretilen temel özet

Koşullu posterior için 16./50./84. yüzdelikler:

| Nicelik | 16. yüzdelik | Medyan | 84. yüzdelik |
|---|---:|---:|---:|
| R(1.4 M☉), km | 11.6702193 | 12.4051369 | 13.0279178 |
| Λ(1.4 M☉) | 303.4738 | 469.9656 | 603.9763 |
| R(2.073 M☉), km | 11.4231470 | 12.1257951 | 12.7350576 |
| Mmax, M☉ | 2.0796513 | 2.1951397 | 2.3917976 |

Önem ağırlığı etkin örnek sayısı (ESS) `8884.995132/10000`; tarihsel düzeltilmiş eski kaynak örnek ağırlığı ESS `425907.933/1600920`. Yerel ve Actions metriklerinin en büyük mutlak farkı `1e-8` altındadır; Actions çıktısı tarihsel kayıtla kendi tolerans kontrollerini de geçti. Ayrı flow/KDE çapraz kontrolü de yapıldı; flow ESS `8842.5312`.

## Bilimsel kapsam

Güncelleme Legred PSR+GW+NICER EOS örneklemini korur ve eski J0740 kaynağı terimini Salmi 2024 yoğunluk oranıyla değiştirir. Aynı NICER fotonları iki bağımsız likelihood olarak çarpılmadı. Bununla birlikte sonuç seçilmiş Legred GP-EOS önseline, kütlede uniform popülasyon varsayımına ve KDE/flow yaklaşık kaynak yoğunluklarına koşulludur. `final_physical_eos_bayes` / tam fiziksel EOS Bayes hesabı `NOT_RUN`; bu çalışma native event-level X-PSI yeniden analizi veya APR4 yedi-EOS Bayes sonucu değildir.

F48–F51 doğrudan RNS C/GR çalışmaları ve 168 yıldızlık kayıt bu çalışmada değiştirilmedi. F52 WFF1 maksimum kütle/dönme kararlılığı ayrı görev olarak kalır. Tarihsel kaynak kodu: [`run_final_weighted_old_source_update.py`](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/blob/science/j0740-apr4-firstlaw-gr-pilot-20261117/research/j0740/historical_20261025/run_final_weighted_old_source_update.py); ayrı Actions uygulaması: [`reproduce_historical_legred_update.py`](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/blob/science/j0740-apr4-firstlaw-gr-pilot-20261117/research/j0740/historical_20261025/reproduce_historical_legred_update.py). Kayıt: [Issue #280](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/280).

Makinece okunur kanıtlar aynı klasörde: ham veri doğrulaması, yerel yürütme manifesti/logu, Actions sonuç/manifest/kaynak hash’leri ve bağımsız karşılaştırma JSON’u.
