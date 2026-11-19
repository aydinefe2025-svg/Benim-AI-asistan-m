# A01.01.51 — F68: ayrı MPA1-PCHIP-COLD EOS ile gerçek dönen GR yıldızları

**19 Kasım 2026 · F67'yi izleyen YENİ doğrudan C/RNS sayısal fizik deneyi.**

## Fiziksel model ve kabul sınırı

Model: `MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL`. **Özgün MPA1 değildir; F42 değildir.** F67 termodinamik tablo SHA-256 `d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22`. RNS için 196 noktalık aynı türetilmiş EOS tablosu kullanıldı; SHA-256 `5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16`. F67'nin ilk-yasaya göre n/n0 şekli korunurken `n0` keyfi bir pozitif referans ile sayısal RNS formatına dönüştürüldü: **RNS M0 fiziksel baryonik kütle değildir**.

## Yeni gerçek 346,536369 Hz tam-GR dönen yıldız sonuçları

| M (M☉) | 151×301 R_eq spin (km) | 151×301 statik R (km) | Bağımsız statik TOV R (km) | 201×401 R_eq spin (km) | İnce−kaba dönme R (m) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2.073 | 12.535416706 | 12.406615643 | 12.406156505 | 12.535109151 | -0.3076 |
| 2.175 | 12.444887058 | 12.325323021 | 12.322892393 | — | — |
| 2.200 | 12.417323740 | 12.299531818 | 12.296156984 | — | — |
| 2.250 | 12.352711910 | 12.237380270 | 12.232612022 | 12.351531456 | -1.1805 |

**İki uzaysal ızgara sonucu:** Maksimum spin R_eq farkı `1.180454 m`, maksimum statik R farkı `3.681111 m` (2 hedefte karşılaştırıldı); her iki C binary **birebir aynı EOS tablo baytlarını** okudu. Bunlar tam model belirsizliği veya gözlemsel hata çubuğu değildir. Kaba RNS statik kütle-yarıçap değerleriyle 4 kütlede bağımsız Python ilk-yasa EOS TOV farklarının maksimumu `4.768248 m`.

**Özgün EOS ile model farkı:** F62 özgün MPA1'in 196 düğümlü ayrı orijinal türetilmiş tablosundaki dönen yıldızlarla F68 alternatif RNS çapraz-farkı `+2,12 m (2,073 M☉)` ile `−5,69 m (2,250 M☉)` arasında. F61–F67 statik TOV farkının −45,39m olmasıyla **bunları eşitleyip fiziksel EOS ölçüm hassasiyeti çıkarmak yanlış**; farklı kaynak tablolarının, enterpolasyonların ve çözüm prosedürünün etkisi vardır.

## Kaynak, test ve SHA makbuzları

- GitHub PR #633 (ilk koşu). Kaba 151×301 ve ince 201×401 RNS-C full-GR gerçek derleme; C denklemlerine **dokunulmadı**, yalnız stdout hassasiyet biçimi değiştirildi.
- 18/18 fail-closed bilimsel birim testi; iki gerçek C çözüm işi, PR'nin üç workflow kontrolü PASS (son merge commit/CI ayrıca kanıtlandıktan sonra Notion makbuzuna yazılır).
- CI kaba ZIP SHA256 `b4649db1180c04278dd37936819b5f2b32f36dd09e223589893bdeb7d7a374cf`; ince ZIP SHA256 `e9d1bd332ea7168182333c2206247f980791c073c473082fd30ed31ceb6c21bd` (ZIP CRC PASS).
- Ham coarse sonuç JSON SHA `addf2967955bbc2dada48a981027cc64aeb8349c9380060e491f18f30f04196b`; fine JSON SHA `91ee06034bf170905fc71e2d5a1b01a338bb20086f6ed249a50de5c9c7536507`; bağımsız static TOV JSON SHA `8aaea404554c1c06226b46f5a6d0f0e29062fb4b194b0432a382641a6cb88b25`.

## Kapatılmamış fizik

Bu hesap **fiziksel kabuk P=0 eşlemesini**, baryon kimyasal potansiyel µ0/n0 ve M0 fiziksel kalibrasyonunu, F67 alternatif için küresel sabit-J kararlılığı, özgün NICER/XMM-Newton 12.9GB foton X-PSI nuisance likelihood'unu veya **yedi özgün nükleer EOS Bayes** hesabını **yapmadı**. Sayısal RNS yıldız başarısı, EOS kabulü veya gözlemsel çıkarım başarısı diye yeniden adlandırılmayacaktır.

Rapor ve kaynak JSON/CSV/EOS dosyaları kanonik A01.01.51'de ve GitHub F68 dalında SHA-256 ile korunacak; F58–F67'ye dokunulmayacak.

