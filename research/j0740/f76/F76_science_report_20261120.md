# A01.01.51 / PSR J0740+6620 — F76: tüm özgün 323 dönen RNS yıldızında fiziksel EOS kaynak-düğüm kabulü

**20 Kasım 2026 — yeni kaynak-kilitli gerçek veri deneyi.** WFF1/WFF2 zaman aşımı kurtarma (PR #670), 323 gerçek yıldızın ilk üretimi, F38 altı KDE ve eksik kütle üst sınır ispatı (PR #679), 2,073 M☉ F75 kaynak örnekleri (PR #681) **yeniden üretilmedi**. Bu analiz, kaynakta SHA-256 ile kilitlenmiş tam yedi `JESTER/LALSimulation` EOS `.npz` dosyası ve 323 adet **gerçek, dönme frekansı 346,536369 Hz olan** RNS C yıldızını baştan sona **yeni bir fizik kabul sorusuyla** tarar.

## Sonuç: orijinal kaynak-nümerik EOS'da her yıldızın merkez yoğunluğuna kadar ihlal var mı?

| Özgün EOS | Gerçek C yıldızı | En az bir kaynak ihlali | Kaynak düğümlerinde ihlal görülmedi* | Kök neden |
| --- | ---: | ---: | ---: | --- |
| APR4_EPP | 48 | 19 | 29 | 19 daha yüksek yoğunluk merkezli yıldızın içi, kaynakta ışıküstü cₛ² düğümünü içeriyor |
| ENG | 48 | 48 | 0 | Düşük basınçta negatif cₛ²/enerji türev anomalisine ek yüksek yoğunluk ışıküstü bölge |
| MPA1 | 48 | 48 | 0 | Düşük basınçta negatif cₛ² ve tek enerji-azalan kaynak aralığı |
| MS1 | 48 | 48 | 0 | Düşük basınçta negatif cₛ² ve tek enerji-azalan kaynak aralığı |
| MS1B | 48 | 48 | 0 | Düşük basınçta negatif cₛ² ve tek enerji-azalan kaynak aralığı |
| WFF1 | 41 | 41 | 0 | Düşük basınç kaynak anomalisi; yüksek merkezli yıldızlarda ışıküstü cₛ² de var |
| WFF2 | 42 | 42 | 0 | Düşük basınç kaynak anomalisi; yüksek merkezli yıldızlarda ışıküstü cₛ² de var |
| **Toplam** | **323** | **294** | **29** | **İhlal: %91,02; yalnız düğüm geçişi: %8,98** |

\* **PASS_KNOTS_ONLY_UNCERTIFIED:** Orijinal EOS'un örneklenmiş düğümlerinde yıldız merkezine dek `0 ≤ cₛ²/c² ≤ 1` gözlendi. **Düğümler arasında, kabuk yüzeyinde, sabit-J dönme kararlılığında veya özgün mikrofizikte sürekli bir fiziksel sertifika DEĞİLDİR.** Özgün EOS uygulamasında gözlenen fizik dışılık doğrudan gerçek mikrofizik teorisinin yanlışlandığı anlamına gelmez: F66, altı modelin düşük-basınç negatif türevinin ham artan basınç/enerji tablosundan değil LALSuite log–log kübik interpolasyonundan üretildiğini doğrudan göstermiştir.

## Yeni ölçüm

- Her orijinal yıldızın `central_energy_density_g_cm3` değerinden merkeze kadarki gerçek EOS enerji düğümleri seçildi; `cs2<0`, `cs2>1`, `Δε(P)≤0` sayıldı. Kaynak düğümü **merkezin üstündeyse**, o yıldız için bu düğümden fiziksel dışlama yapılmadı. Gerçek yıldızın mevcut yüzey–merkez EOS temsilinde bir uygunsuz düğüm varsa yalnız **o kaynak uygulaması** için ret konuldu.
- Kaynak `.npz` dosyaları ve gerçek RNS JSON'ları, değişmez manifest SHA-256'larıyla eşleştirildi. 323 kaydın tamamında model kimliği, pozitif ve sonlu merkez/kütle bilgisi, C çözücü etiketleri, dönen yıldızın hedef frekansına izin verilen artığı kontrol edildi.
- APR4_EPP orijinal kaynak tablosunda ilk örneklenmiş `cₛ²>1` enerji düğümü ≈ **2,029865 × 10¹⁵ g/cm³**. Orijinal 48 C yıldızın **29'u** merkez yoğunluğunda bu düğümü içermiyor, **19'u** içeriyor. Geçen 29 yıldız arasında en büyük kaydedilmiş kütle ≈ **2,134305873 M☉**. Bu **kütle kesimi, sürekli sınır veya dinamik kararlılık teoremi değildir**; örnek yıldızların kaydedilmiş en büyük değeridir.
- ENG/MPA1/MS1/MS1B/WFF1/WFF2'nin kaynak EOS basınç-gridinde altı ortak düşük-basınç noktası anomalisini ve altı enerji-azalan aralığı gizlemeden saydı. Bu sayede kaynak türü ile farklı fiziksel EOS önerileri birbirine karıştırılmıyor.

## Bilimsel yorum: eski sıralamayla çelişki yok

MPA1 > ENG > APR4_EPP sırası [PR #679](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/679) içindeki *kaynak F38 iki-boyutlu KDE* ve mevcut yedi sayısal EOS hipotezine koşulludur; eksik RNS kütlelerin olası katkısı bu **koşullu sıralamayı** değiştirmez. Ancak MPA1 ve ENG mevcut kaydedilmiş **orijinal numerik EOS temsiliyle** kaynak-düğüm fizik kabulünü geçmedi. Bunun anlamı APR4_EPP'nin artık otomatik %100 Bayes olasılığı elde ettiği değildir. **Fizik kabul önseli ve farklı tutarlı nükleer EOS modeli kurulmadan yeniden normalize edilmiş posterior üretilmemiştir.**

## Bilimsel açık sınırlar

1. Gerçek kaynak `p,e,cs2` düğümleri arasındaki **sürekli** `0≤dP/dε≤1`, H(P), n(P), kimyasal potansiyel ve kabuk–çekirdek geçişi: henüz bağımsız fiziksel kabul edilmiş EOS yok. Alternatif PCHIP sadece tanı aracı; orijinal model adı altında sessiz düzeltme YASAK.
2. Kaynağın global sabit-J dönme kararlılığı, her fiziksel dalın sınırları: NOT_ESTABLISHED.
3. Orijinal Salmi 2024 STU NICER+XMM faz/enerji kanal veri ürünü, tam X-PSI olasılığı ve nuisance marjinalizasyonu: NOT_RUN. Arşivdeki F38 posterior/önsel KDE yüzeyleri **özgün foton olaylarından hesaplanan olabilirlik değildir**. Aynı radyo-kütle önseli iki kez kullanılmamalı.

## Kaynak ve yeniden üretilebilirlik

- Özgün 7 EOS ve orijinal RNS kanıt ZIP'i: `J0740_ORIGINAL_7_ROTATING_GR_WFF_RESCUE_F38_FULL_EVIDENCE_20261119.zip`, SHA-256 `0306d0ed4b15f25c4831433aecb5f536cefd803082402a31c6461ea6750559bb`.
- Orijinal JESTER kaynak commit'i: `e6768650ce992abfd1153a6833857572fe5cd230`. EOS `.npz` dosyaları ve 7 gerçek 346 Hz C-star JSON ZIP'leri tekil SHA-256 manifestleriyle fail-closed doğrulanır.
- Bütün 323 yıldız için ayrı satırları, ihlal sayısını, ilk kaynak ihlal yoğunluklarını ve kaynak hash'lerini içeren tam makine-okunur JSON: `F76_323_causality_20261120.json`.
- 12 yeni adversarial regresyon testi, önceki F75 SHA/mass/physics guard regresyon testlerinden bağımsız çalışır.
- Bilimsel referans: [hızın sınırı ve termodinamik stabilite derlemesi](https://link.springer.com/article/10.1007/s43673-021-00011-6); [Salmi et al. 2024 ham X-PSI veri/kod](https://zenodo.org/records/10519473).

**Karar:** `F76_SOURCE_SAMPLED_323_STAR_POPULATION_CLASSIFIED`; `PHYSICAL_EOS_CERTIFICATION=NOT_ESTABLISHED`; `PHOTON_EVENT_LEVEL_XPSI=NOT_RUN`. Aynı F75 deneyi tekrarlamak yerine 323 gerçek kaydın tamamına uygulanan yeni bir kaynak-ihlali etki denetimidir.