# PSR J0740+6620 — 19 Kasım 2026: Yedi özgün dönen EOS, hesaplanmamış kütlelerde koşullu sıralama üst-sınır sertifikası

**Bu yeni kanıt, WFF1/WFF2 yüksek yoğunluk zaman aşımı sorununu çözülmüş kabul eden orijinal 323 gerçek RNS yıldızına dayanır. Kaynak C yıldızları ve 12,9 GB Salmi arşivi tekrar çalıştırılmadı.**

## Yeni somut bilimsel sonuç
Matematiksel olarak mümkün olan **her türlü hesaplanmamış RNS kütle bölgesi katkısı** eklense bile, özgün 6 F38 gözlem KDE modelinin 6/6 seçeneğinde **birinci MPA1, ikinci ENG, üçüncü APR4_EPP** kalıyor. Bu, 7 özgün sayısal EOS *koşullu* model sıralaması için bir üst sınır denetimidir; gerçek nükleer fiziksel geçerlilik veya foton düzeyinde X-PSI Bayes sonucu değildir.

| Düşürülmemesi gereken karşılaştırma | Altı KDE boyunca en küçük fark (normalize edilmemiş I=L/Z) |
| --- | ---: |
| MPA1 eksi en avantajlı herhangi rakip | **0.490589** |
| ENG eksi üçüncülük adayının en avantajlı katkısı | **0.802691** |
| APR4_EPP eksi daha düşük adayının en avantajlı katkısı | **0.028363** |

## Eksik kütleler için denklemler
Özgün F38 kaynak KDE alanları iki-boyutlu **bilineer** enterpolasyonla değerlendirilir. Her kaydedilmiş kütle noktasında `U(m_j)=max_R L_F38(m_j,R)` tanımlandı. Kütle düğümleri arasında `U(m)` bu maksimumların lineer enterpolasyonudur. Bilineer alanın her yarıçap kesiti için `0≤L_F38(m,R)≤U(m)` elde edilir. Bu nedenle gerçek RNS dalı `[M_min,i,M_max,i]` dışında ne büyüklükte kaynak olabilirlik olduğu bilinmese dahi, katkı **en fazla** `B_i=∫_{M dış destek}π_radio(M)U(M)dM` olabilir. RNS dalı dışındaki fiziksel yıldızları uydurmak yerine onlara *bu aşırı cömert üst sınır* verildi. F38 dikdörtgen desteği dışında lineer interpolatörün `fill_value=0` özelliği korundu.

Radyo-kütle önseli `truncnorm(μ=2.082 M☉,σ=0.0703 M☉, ±5σ)` olarak **bir kez** kullanıldı. Her kütle düğümü arasındaki üst-zarf `U(m)` lineer olduğundan Gaussian × lineer integral, normal CDF/PDF ilk-moment antitüreviyle analitik hesaplandı. Sayısal Simpson yaklaşımı ile eksik düğüm tahmini yapılmadı.

Her model için gerçek RNS hesaplanan `S_i` ve bilinmeyen ek katkı `δ_i∈[0,B_i]` olmak üzere, belirli altı KDE varyantının her birinde tüm yedi adayın sırasını değerlendirdik. Örneğin MPA1’in birinciliği için tüm rakiplere karşı `S_MPA1 > S_j+B_j` kontrol edildi; daha sonra ENG ikinciliği ve APR4_EPP üçüncülüğü aynı şekilde denetlendi.

## Orijinal kaynak hesaplanmamış bölge koşullu olasılık sınırları

**Önemli:** Bu sınırlar altı ayrı KDE varyantı ve kaynakta bilineer yoğunluk varsayımı içindeki *en ihtiyatlı birleşik min–max* değerlerdir; fiziksel Bayes güven aralığı veya hata çubuğu değildir.

| EOS | Olası en küçük ağırlık | Olası en büyük ağırlık |
| --- | ---: | ---: |
| MPA1 | 32.63% | 41.03% |
| ENG | 25.28% | 32.07% |
| APR4_EPP | 8.12% | 14.85% |
| WFF2 | 5.51% | 10.22% |
| MS1B | 5.76% | 6.97% |
| MS1 | 4.39% | 5.56% |
| WFF1 | 0.48% | 8.76% |

## Kaynak ve doğrulama
- Girdi tek ZIP: `J0740_ORIGINAL_7_ROTATING_GR_WFF_RESCUE_F38_FULL_EVIDENCE_20261119.zip`, gerçek kaynak SHA-256 `0306d0ed4b15f25c4831433aecb5f536cefd803082402a31c6461ea6750559bb`.
- ZIP içindeki gerçek F38 iki-boyutlu olabilirlik kaynak SHA-256 `4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307`.
- 6 × 401 kütle düğümlü F38 satır maksimumları ile yedi özgün RNS destek aralığı ve eski 42 kaynak skorunun birlikte kanonik SHA-256 kilidi `4d7a16e5d6c1eada208ca49da756245a348ae725917a4b1ba77bdeb026815924`.
- Kaynağa karşı adversarial 12 Python testi: Gaussian–lineer tam integral vs bağımsız `scipy.integrate.quad`; bilineer 2B alanın satır maksimumu; hesaplanmış modellerin destek dışı sıfır katkısı; 6 kaynak KDE gerçek sıralama; SHA değişikliklerinde fail-closed. **12/12 PASS**.
- Sayısal/model hata güvencesi: kaynak destek maskesi, yalnız bu F38 interpolatörü ve mevcut gözlem/model varsayımları çerçevesinde kanıt; orijinal RNS C kaynak seri kimliği PR #670.
- **Fizik kabulü yapılmış EOS posterioru değildir.** F65/F66 düşük-P LAL log-log kübik türev anomalisi, bazı özgün EOS yüksek yoğunluk nedensellik sorunları, dönen yıldız global sabit-J kararlılığı ve kaynak-foton X-PSI olabilirliği bu sıralama teoremiyle çözülmüş değildir.

## Yeniden üretim (12,9 GB foton arşivi gerekmez)

`python -m unittest -v test_j0740_missing_mass_upper`
`python j0740_missing_mass_upper.py --envelopes missing_rank/J0740_source_F38_rows_max_envelopes.json --outdir rebuilt`

Tam F38 2B kaynak alanından zarfı tekrar oluşturmak için: `python j0740_missing_mass_upper.py --original-evidence-zip /A01.01.51/PSR_J0740+6620/original_spin_recovery/J0740_ORIGINAL_7_ROTATING_GR_WFF_RESCUE_F38_FULL_EVIDENCE_20261119.zip --outdir rebuilt` (burada Library yolundan indirilen dosyayı yerel olarak göstermelisiniz).
