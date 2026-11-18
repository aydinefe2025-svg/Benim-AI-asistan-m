# F50 — PSR J0740+6620: 2026 manyetik sıcak-bölge modeliyle bağımsız *yorum duyarlılığı* denetimi

18 Kasım 2026 — A01.01.51. F49 sonrası yeni gözlemsel sistematik taraması; yeni foton/X-PSI olabilirlik hesabı **değil**.

## Yeni kaynak: Huang, Salmi & Chen (29 Eylül 2026)
- Fiziksel olarak modellenen kaymış dipol için **M=2,059(+0,068/−0,069) M☉**, **R=13,28(+1,47/−1,07) km** (marginal %68). https://arxiv.org/abs/2609.37928
- Aynı çalışmanın merkezlenmiş dipol+kuadrupol modeli **R=17,46(+1,57/−1,48) km** çıkarıyor; kaymış dipol modeli seçilmiş önseller altında **Δln Z=5,65** (Bayes faktörü yaklaşık 285) ile tercih ediliyor. **Bu faktör iki sıcak-bölge/manyetik geometri modelinin karşılaştırmasıdır, nükleer EOS Bayes faktörü değildir.**
- 2026 çalışması Salmi 2024 ile **aynı 2018–2022 NICER olay listesini ve XMM verilerini** kullanıyor (makale II.1). Dolayısıyla F38 ile 2026 sonucunu iki bağımsız veri kümesiymiş gibi olasılık çarpımıyla birleştirmek **çifte sayımdır**.
- Çalışma, nominal cihaz kalibrasyonu kullanmış ve çapraz-kalibrasyon faktörlerini örneklememiştir. Sıcak-bölge fizik varsayımına bağlıdır; yeni posterior örnekleri teyit edilmeden tam EOS kanıtı oluşturmaz.

## Kaynağı SHA ile kilitlenmiş yedi gerçek C/GR yıldızının tek kütlelik karşılaştırması

F44 kaynak ZIP SHA-256 `b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98` gerçek veri kaynağıdır. M=2,073 M☉, f=346,536369 Hz. Bu iki ayrı makalenin **marjinal R %68 aralıklarıyla salt görsel/sayısal kontrolüdür**, model dışlama testine dönüştürülmez.

| Yeni F42 EOS adayı | R_eq (km) | Salmi 2024 %68 (11,61–13,77) | Huang 2026 kaymış dipol %68 (12,21–14,75) |
|---|---:|:---:|:---:|
| WFF1 | 9.948243 | dışında | dışında |
| WFF2 | 10.622215 | dışında | dışında |
| APR4_EPP | 10.769799 | dışında | dışında |
| ENG | 11.498900 | dışında | dışında |
| MPA1 | 12.512740 | içinde | içinde |
| MS1B | 14.872589 | dışında | dışında |
| MS1 | 15.032570 | dışında | dışında |

**ÖNEMLİ:** “dışında” ibaresi yalnız belirli bir tek kütledeki R_eq tahmininin başka model altında elde edilmiş **marjinal** %68 aralık dışında olduğunu söyler. Ne gerçek EOS modelinin reddi ne de yıldızın fiziksel yapı kanıtıdır. 2026 kaynak R-M korelasyonu, ölçüm/geometri önselleri, örnekleme posterioru ve birbirinden bağımsız olmayan fotonlar bu tablodan çıkarılamaz.

## Doğrulanmış iş ve açık fizik
- F44 gerçek 7 RNS C kökü SHA kilitli okundu, kütle/frekans artıklarının ve 30 m iki-ağ toleransının denetimi PASS.
- F50 **6/6 otomatik test PASS**; makalelerin %68 marjinal değerleriyle tarih/önsel ve aynı-foton riski açık işaretli.
- Sonradan çıkarılacak makale posterior örnekleri yoksa 2026 çalışmasının R-M yüzeyi türetilemez; yalnız medyan ve %68 güvenilirlik aralığından yaklaşık Gaussian EOS Bayes üretmek bilimsel olarak geçerli değildir.
- Tam 7 orijinal nükleer EOS fiziksel kabul, küresel sabit-J kararlılık, özgün foton-seviyesi X-PSI ve tüm kütle desteği üzerindeki model kanıtı **NOT_RUN / NOT_ESTABLISHED**.

## Birincil kaynaklar
- Huang, Salmi & Chen 2026: https://arxiv.org/abs/2609.37928
- Salmi et al. 2024: https://doi.org/10.3847/1538-4357/ad5f1f
- Dittmann et al. 2024: https://arxiv.org/abs/2406.14467
- Riley et al. 2021: https://arxiv.org/abs/2105.06980
- Miller et al. 2021: https://ntrs.nasa.gov/citations/20210026095

**Sonuç:** F49’daki MPA1 koşullu avantajı, farklı sıcak-bölge fiziğinin belirlediği model varsayımlarına karşı **doğrudan nihai EOS kazananı** olarak kabul edilemez. Aşama bir *sistematik-duyarlılık denetimi*; Bayesian sonucun yeni kanıtı değil.
